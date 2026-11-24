/* Off-device filesystem fixtures only; never opens a device or service. */
#define _GNU_SOURCE
#include "output_dsp_control.h"
#include <assert.h>

static struct od_params parameters(void) {
    struct od_params p={0};p.eq_on=p.sub_on=1;p.wet=25;p.maxhz=56;p.minhz=25;
    p.low=p.high=100;p.threshold=-48;p.attack=12;p.release=100;
    for(int i=0;i<8;i++){p.bands[i][0]=90*(i+1);p.bands[i][1]=.707f;}
    p.bands[5][2]=-6;return p;
}
static void save(const char *path) {
    struct od_params p=parameters();float row[OD_VALUES];memcpy(row,&p,sizeof row);
    FILE*f=fopen(path,"w");assert(f);
    for(int i=0;i<OD_PAIRS;i++){for(int j=0;j<OD_VALUES;j++)fprintf(f,"%.8g ",row[j]);fputc('\n',f);}
    assert(!fclose(f));
}
static void check(const char *path,unsigned mask,int eq,int sub) {
    od_poll(path,48000,mask);unsigned version=0;struct od_cfg c;
    assert(od_receive(0,&c,&version));assert(c.eq==(unsigned)eq&&c.sub==(unsigned)sub);
}
int main(void) {
    (void)od_control_poll;
    char dir[]="/tmp/od-lifecycle-XXXXXX";assert(mkdtemp(dir));
    char path[256],lease[256],link[256];
    snprintf(path,sizeof path,"%s/config",dir);snprintf(lease,sizeof lease,"%s/lease",dir);snprintf(link,sizeof link,"%s/link",dir);
    save(path);check(path,0,0,0);check(path,1,OD_FEATURE_EQ,0);check(path,2,0,OD_FEATURE_SUB);check(path,3,OD_FEATURE_EQ,OD_FEATURE_SUB);
    /* Persisted enabled settings alone do not authorize the next boot. */
    check(path,0,0,0);save(path);check(path,3,OD_FEATURE_EQ,OD_FEATURE_SUB);
    FILE*f=fopen(path,"w");assert(f);fputs("nan 1 broken\n",f);fclose(f);check(path,3,0,0);
    save(path);check(path,3,OD_FEATURE_EQ,OD_FEATURE_SUB);
    f=fopen(path,"a");assert(f);fputs("trailing token",f);fclose(f);check(path,3,0,0);
    unlink(path);assert(!mkfifo(path,0600));check(path,3,0,0);unlink(path);
    save(lease);assert(!symlink(lease,path));check(path,3,0,0);unlink(path);
    save(path);check(path,3,OD_FEATURE_EQ,OD_FEATURE_SUB);unlink(path);check(path,3,0,0);
    const char *boot="11111111-2222-3333-4444-555555555555";
    f=fopen(lease,"w");assert(f);fprintf(f,"OD1 %s 100.0 3 48000\n",boot);fclose(f);
    unsigned mask,rate;
    assert(od_record(lease,boot,102,&mask,&rate)&&mask==3&&rate==48000);
    assert(!od_record(lease,boot,104,&mask,&rate));
    assert(!od_record(lease,boot,99,&mask,&rate));
    assert(!od_record(lease,"other-boot",102,&mask,&rate));
    assert(!symlink(lease,link));assert(!od_record(link,boot,102,&mask,&rate));unlink(link);
    f=fopen(lease,"w");assert(f);fprintf(f,"OD1 %s nan 3 48000\n",boot);fclose(f);
    assert(!od_record(lease,boot,102,&mask,&rate));
    unlink(lease);assert(!mkfifo(lease,0600));assert(!od_record(lease,boot,102,&mask,&rate));unlink(lease);
    struct od_params p=parameters();p.attack=NAN;struct od_cfg c;od_prepare(&c,&p,48000);assert(!c.eq&&!c.sub);
    assert(!rmdir(dir));puts("output DSP lifecycle tests passed");
    return 0;
}
