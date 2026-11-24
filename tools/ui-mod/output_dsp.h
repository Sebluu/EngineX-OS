#ifndef SC_OUTPUT_DSP_H
#define SC_OUTPUT_DSP_H
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include "output_dsp_features.h"

enum { OD_PAIRS=4, OD_FILTERS=10 };
struct od_bq { float b0,b1,b2,a1,a2; };
struct od_z { float z1,z2; };
struct od_params {
    float eq_on,hp,sub_on,wet,maxhz,minhz,low,high,threshold,attack,release;
    float bands[8][3];
};
/* 11 + 24 = 35 floats; file rows follow this exact order. */
#define OD_VALUES 35
_Static_assert(sizeof(struct od_params)==OD_VALUES*sizeof(float),"config layout");
struct od_cfg {
    unsigned rate, eq, sub;
    float wet, level[2], threshold, attack, release;
    unsigned min_period[2], max_period[2];
    struct od_bq filters[OD_FILTERS], source[2][2], hp[2], lp[2];
};
struct od_state {
    struct od_cfg c;
    struct od_z eq[2][OD_FILTERS], source[2][2], hp[2], lp[2];
    float previous[2], envelope[2], sign[2];
    unsigned age[2];
};
struct od_mail {
    unsigned sequence;
    uint32_t words[sizeof(struct od_cfg)/4];
};
_Static_assert(sizeof(struct od_cfg)%4==0,"mailbox layout");
_Static_assert(__atomic_always_lock_free(4,0),"audio mailbox must be lock-free");
static struct od_mail od_mail[OD_PAIRS];
static struct od_state od_now[OD_PAIRS],od_old[OD_PAIRS];
static unsigned od_version[OD_PAIRS],od_fade[OD_PAIRS];
static inline float od_abs(float x) { return x<0?-x:x; }
static inline float od_clamp(float x,float lo,float hi) {return x<lo?lo:x>hi?hi:x;}
static inline float od_tick(const struct od_bq *b,struct od_z *s,float x) {
    float y=b->b0*x+s->z1,z1=b->b1*x-b->a1*y+s->z2,z2=b->b2*x-b->a2*y;
    s->z1=od_abs(z1)<1e-20f?0:z1; s->z2=od_abs(z2)<1e-20f?0:z2;
    return y;
}
/* RBJ biquads: only the ordinary control worker calls libm. */
static struct od_bq od_filter(int type,double hz,double q,double db,unsigned rate) {
    if (hz<=0 || (type<3 && db==0)) return (struct od_bq){1,0,0,0,0};
    hz=fmin(hz,rate*.46); double w=6.283185307179586*hz/rate, s=sin(w),c=cos(w);
    double A=pow(10,db/40),al=s/(2*q),b0,b1,b2,a0,a1,a2;
    if(type==0){b0=1+al*A;b1=-2*c;b2=1-al*A;a0=1+al/A;a1=-2*c;a2=1-al/A;}
    else if(type==1||type==2){
        double t=2*sqrt(A)*al,m=A-1,p=A+1;
        if(type==1){b0=A*(p-m*c+t);b1=2*A*(m-p*c);b2=A*(p-m*c-t);a0=p+m*c+t;a1=-2*(m+p*c);a2=p+m*c-t;}
        else {b0=A*(p+m*c+t);b1=-2*A*(m+p*c);b2=A*(p+m*c-t);a0=p-m*c+t;a1=2*(m-p*c);a2=p-m*c-t;}
    } else {
        int hp=type==3;b0=(1+(hp?c:-c))*.5;b1=(hp?-2:2)*b0;b2=b0;a0=1+al;a1=-2*c;a2=1-al;
    }
    return (struct od_bq){b0/a0,b1/a0,b2/a0,a1/a0,a2/a0};
}
static int od_valid(const struct od_params *p);
static void od_prepare(struct od_cfg *c,const struct od_params *p,unsigned rate) {
    memset(c,0,sizeof *c); c->rate=rate;
    if(rate<32000||rate>192000||!od_valid(p))return;
    int eq_changed=p->hp>=10;
    for(int i=0;i<8;i++)if(p->bands[i][2]!=0)eq_changed=1;
    c->eq=OD_FEATURE_EQ && p->eq_on!=0 && eq_changed;
    c->sub=OD_FEATURE_SUB && p->sub_on!=0 && p->wet>0 && (p->low>0 || p->high>0);
    if (!c->eq && !c->sub) return;
    c->wet=p->wet*.01f;c->level[0]=p->low*.01f;c->level[1]=p->high*.01f;
    c->threshold=pow(10,p->threshold/20);
    c->attack=1-exp(-1/(rate*p->attack*.001));c->release=1-exp(-1/(rate*p->release*.001));
    for(int i=0;i<OD_FILTERS;i++)c->filters[i]=(struct od_bq){1,0,0,0,0};
    if(c->eq){
        for(int i=0;i<8;i++)c->filters[i]=od_filter(i==0?1:i==7?2:0,p->bands[i][0],p->bands[i][1],p->bands[i][2],rate);
        if(p->hp>=10){c->filters[8]=od_filter(3,p->hp,.541196,0,rate);c->filters[9]=od_filter(3,p->hp,1.306563,0,rate);}
    }
    if(c->sub)for(int j=0;j<2;j++){
        double lo=fmax(j?72:30,p->minhz*2),hi=fmin(j?160:72,p->maxhz*2);
        if(hi<=lo){c->level[j]=0;continue;}
        c->min_period[j]=(unsigned)(rate/hi);
        c->max_period[j]=(unsigned)(rate/lo)+1;
        c->source[j][0]=od_filter(3,lo,.707,0,rate);c->source[j][1]=od_filter(4,hi,.707,0,rate);
        c->hp[j]=od_filter(3,p->minhz,.707,0,rate);c->lp[j]=od_filter(4,p->maxhz,.707,0,rate);
    }
}
/* Single publisher; atomic words avoid races even if publication interrupts a read.
   One attempt per block, no spin, mutex, allocation or syscall on the audio path. */
static void od_publish(unsigned p,const struct od_cfg *c) {
    struct od_mail *m=&od_mail[p]; uint32_t w[sizeof(*c)/4]; memcpy(w,c,sizeof w);
    unsigned seq=__atomic_load_n(&m->sequence,__ATOMIC_SEQ_CST);
    __atomic_store_n(&m->sequence,seq+1,__ATOMIC_SEQ_CST);
    for(unsigned i=0;i<sizeof w/4;i++)__atomic_store_n(&m->words[i],w[i],__ATOMIC_SEQ_CST);
    __atomic_store_n(&m->sequence,seq+2,__ATOMIC_SEQ_CST);
}
static inline int od_receive(unsigned p,struct od_cfg *c,unsigned *version) {
    struct od_mail *m=&od_mail[p];unsigned a=__atomic_load_n(&m->sequence,__ATOMIC_SEQ_CST);
    if(!a||(a&1)||a==*version)return 0;
    uint32_t w[sizeof(*c)/4];
    for(unsigned i=0;i<sizeof w/4;i++)w[i]=__atomic_load_n(&m->words[i],__ATOMIC_SEQ_CST);
    if(a!=__atomic_load_n(&m->sequence,__ATOMIC_SEQ_CST))return 0;
    memcpy(c,w,sizeof w);*version=a;return 1;
}
static inline void od_sample(struct od_state *s,float *l,float *r) {
    struct od_cfg *c=&s->c;
    if(!c->eq&&!c->sub)return;
    float x=*l,y=*r;
    if(!(od_abs(x)<1e10f))x=0;
    if(!(od_abs(y)<1e10f))y=0;
    if(c->sub){
        float mid=(x+y)*.5f,sub=0;
        for(unsigned j=0;j<2;j++){
            if(c->level[j]==0)continue;
            float v=od_tick(&c->source[j][1],&s->source[j][1],od_tick(&c->source[j][0],&s->source[j][0],mid));
            float a=od_abs(v);s->envelope[j]+=(a-s->envelope[j])*(a>s->envelope[j]?c->attack:c->release);
            if(s->age[j]<c->rate)s->age[j]++;
            if(v>=0&&s->previous[j]<0){
                unsigned n=s->age[j];s->age[j]=0;
                if(n>=c->min_period[j]&&n<=c->max_period[j]&&s->envelope[j]>c->threshold)s->sign[j]=s->sign[j]>0?-1:1;
                else s->sign[j]=0;
            }
            s->previous[j]=v;
            if(s->age[j]>c->max_period[j]+1||s->envelope[j]<c->threshold)s->sign[j]=0;
            float raw=s->sign[j]*s->envelope[j];
            sub+=od_tick(&c->lp[j],&s->lp[j],od_tick(&c->hp[j],&s->hp[j],raw))*c->level[j];
        }
        sub=od_clamp(sub*c->wet,-.20f,.20f);x+=sub;y+=sub;
    }
    if(c->eq)for(int i=0;i<OD_FILTERS;i++){
        const struct od_bq *b=&c->filters[i];
        if(b->b0==1 && b->b1==0 && b->b2==0 && b->a1==0 && b->a2==0)continue;
        x=od_tick(b,&s->eq[0][i],x);y=od_tick(b,&s->eq[1][i],y);
    }
    *l=x;*r=y;
}
static inline int od_process(unsigned p,float*l,float*r,unsigned frames,unsigned rate) {
    if(p>=OD_PAIRS||!l||!r||rate<32000||rate>192000)return 0;
    struct od_cfg c;
    if(od_now[p].c.rate!=rate)od_fade[p]=0;
    if(!od_fade[p]&&od_receive(p,&c,&od_version[p])){
        od_old[p]=od_now[p];memset(&od_now[p],0,sizeof od_now[p]);od_now[p].c=c;
        od_fade[p]=(c.eq||c.sub||od_old[p].c.eq||od_old[p].c.sub)?rate/25:0;
    }
    struct od_state*s=&od_now[p];if(s->c.rate!=rate)return 0;
    if(!s->c.eq&&!s->c.sub&&!od_fade[p])return 0;
    for(unsigned i=0;i<frames;i++){
        float x=l[i],y=r[i],a=x,b=y;od_sample(s,&x,&y);
        if(od_fade[p]){
            if(od_old[p].c.rate==rate)od_sample(&od_old[p],&a,&b);
            float k=(float)od_fade[p]/(rate/25);x+=(a-x)*k;y+=(b-y)*k;--od_fade[p];
        }
        l[i]=x;r[i]=y;
    }
    return 1;
}
static int od_range(float x,float lo,float hi){return isfinite(x)&&x>=lo&&x<=hi;}
static int od_valid(const struct od_params *p){
    if((p->eq_on!=0&&p->eq_on!=1)||(p->sub_on!=0&&p->sub_on!=1)||
       !od_range(p->hp,0,150)||(p->hp>0&&p->hp<10)||
       !od_range(p->wet,0,100)||!od_range(p->maxhz,30,80)||!od_range(p->minhz,15,55)||p->maxhz<p->minhz+5||
       !od_range(p->low,0,100)||!od_range(p->high,0,100)||!od_range(p->threshold,-80,-12)||
       !od_range(p->attack,2,100)||!od_range(p->release,20,500))return 0;
    for(int b=0;b<8;b++)if(!od_range(p->bands[b][0],20,22000)||!od_range(p->bands[b][1],.3,8)||!od_range(p->bands[b][2],-12,12))return 0;
    return 1;
}
#ifndef OD_DSP_ONLY
/* Called only by the existing 80 ms settings worker. Invalid/missing file disables DSP. */
static void od_poll(const char *path,unsigned rate,unsigned enabled) {
    static unsigned previous_rate,previous_enabled;static int have, had_stat;
    static struct stat old_stat;
    static struct od_params previous[OD_PAIRS];
    struct stat st;
    int exists=stat(path,&st)==0;
    if(have&&previous_rate==rate&&previous_enabled==enabled&&exists==had_stat&&
       (!exists||(old_stat.st_dev==st.st_dev&&old_stat.st_ino==st.st_ino&&old_stat.st_size==st.st_size&&
        old_stat.st_mtim.tv_sec==st.st_mtim.tv_sec&&old_stat.st_mtim.tv_nsec==st.st_mtim.tv_nsec&&
        old_stat.st_ctim.tv_sec==st.st_ctim.tv_sec&&old_stat.st_ctim.tv_nsec==st.st_ctim.tv_nsec)))return;
    struct od_params next[OD_PAIRS]={{0}};
    int fd=exists?open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK):-1;
    struct stat opened;
    int regular=fd>=0&&fstat(fd,&opened)==0&&S_ISREG(opened.st_mode)&&opened.st_size>0&&opened.st_size<=8192;
    FILE*f=regular?fdopen(fd,"r"):NULL;
    if(!f&&fd>=0)close(fd);
    int good=f!=NULL;
    if(f){
        for(int p=0;p<OD_PAIRS&&good;p++){
            float row[OD_VALUES];for(unsigned j=0;j<OD_VALUES;j++)if(fscanf(f,"%f",&row[j])!=1){good=0;break;}
            if(good){memcpy(&next[p],row,sizeof row);good=od_valid(&next[p]);}
        }
        if(good){char extra; if(fscanf(f," %c",&extra)==1)good=0;}
        fclose(f);
    }
    if(!good){memset(next,0,sizeof next);for(int p=0;p<OD_PAIRS;p++){next[p].attack=12;next[p].release=100;}}
    had_stat=exists;
    if(exists)old_stat=st;
    for(int p=0;p<OD_PAIRS;p++) {
        if(!(enabled&1))next[p].eq_on=0;
        if(!(enabled&2))next[p].sub_on=0;
        if (have && previous_rate==rate && !memcmp(&next[p],&previous[p],sizeof next[p])) continue;
        struct od_cfg c; od_prepare(&c,&next[p],rate); od_publish(p,&c);
    }
    memcpy(previous,next,sizeof next);have=1;previous_rate=rate;previous_enabled=enabled;
}
#endif /* !OD_DSP_ONLY */
#endif
