#define _GNU_SOURCE
#include "output_dsp.h"
#include <assert.h>
static float left[192000],right[192000];
static void process(unsigned pair,unsigned rate) {
    for(unsigned i=0;i<rate;i+=128)od_process(pair,left+i,right+i,rate-i<128?rate-i:128,rate);
    for(unsigned i=0;i<rate;i++)assert(isfinite(left[i])&&isfinite(right[i]));
}
int main(void) {
    const unsigned rates[]={32000,44100,48000,88200,96000,192000};
    struct od_params p={0};p.sub_on=1;p.wet=70;p.maxhz=56;p.minhz=25;p.low=p.high=100;p.threshold=-60;p.attack=12;p.release=100;
    for(int b=0;b<8;b++){p.bands[b][0]=90*(b+1);p.bands[b][1]=.707f;}
    for(unsigned n=0;n<sizeof rates/sizeof *rates;n++) {
        unsigned rate=rates[n];struct od_cfg c;od_prepare(&c,&p,rate);od_publish(0,&c);
        for(unsigned i=0;i<rate;i++)left[i]=right[i]=.25f*sinf((float)(6.283185307179586*80*i/rate));
        process(0,rate);
        double a=0,b=0;for(unsigned i=rate/2;i<rate;i++){double w=6.283185307179586*40*i/rate;a+=left[i]*cos(w);b+=left[i]*sin(w);}
        assert(4*hypot(a,b)/rate>.008);
        struct od_params eq=p;eq.sub_on=0;eq.eq_on=1;eq.bands[5][0]=3000;eq.bands[5][2]=-6;
        od_prepare(&c,&eq,rate);od_publish(1,&c);
        for(unsigned i=0;i<rate;i++){left[i]=.1f*sinf((float)(6.283185307179586*3000*i/rate));right[i]=0;}
        process(1,rate);for(unsigned i=0;i<rate;i++)assert(right[i]==0);
        eq.bands[5][2]=0;od_prepare(&c,&eq,rate);assert(!c.eq&&!c.sub);od_publish(2,&c);
        for(unsigned i=0;i<rate;i++){left[i]=(float)i/rate;right[i]=-(float)i/rate;}
        assert(!od_process(2,left,right,rate,rate));
        for(unsigned i=0;i<rate;i++)assert(left[i]==(float)i/rate&&right[i]==-(float)i/rate);
    }
    float a=1,b=-1;assert(!od_process(OD_PAIRS,&a,&b,1,48000));assert(a==1&&b==-1);
    assert(!od_process(0,&a,&b,1,8000));assert(a==1&&b==-1);
    od_poll("/nonexistent",48000,0);puts("output DSP sample-rate and stereo tests passed");return 0;
}
