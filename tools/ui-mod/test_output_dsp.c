/* cc -O2 -std=c11 -DOD_FEATURE_EQ=1 -DOD_FEATURE_SUB=1 test_output_dsp.c -lm -o /tmp/test_od && /tmp/test_od */
#include "output_dsp.h"
#include <assert.h>
#define RATE 48000
static float l[RATE],r[RATE];
static struct od_params defaults(void){
    struct od_params p={0};p.wet=70;p.maxhz=56;p.minhz=25;p.low=p.high=100;p.threshold=-60;p.attack=12;p.release=100;
    float hz[]={90,180,350,750,1500,3000,8000,19000};for(int i=0;i<8;i++){p.bands[i][0]=hz[i];p.bands[i][1]=.707;}return p;
}
static void tone(double hz){for(int i=0;i<RATE;i++)l[i]=r[i]=.25*sin(6.283185307179586*hz*i/RATE);}
static double amplitude(double hz){double a=0,b=0;for(int i=RATE/2;i<RATE;i++){double w=6.283185307179586*hz*i/RATE;a+=l[i]*cos(w);b+=l[i]*sin(w);}return 4*hypot(a,b)/RATE;}
static void run(unsigned p){for(int i=0;i<RATE;i+=240)od_process(p,l+i,r+i,240,RATE);for(int i=0;i<RATE;i++)assert(isfinite(l[i])&&isfinite(r[i]));}
int main(void){
    struct od_params p=defaults();struct od_cfg c;assert(od_valid(&p));
    od_prepare(&c,&p,RATE);od_publish(0,&c);tone(80);run(0);
    for(int i=0;i<RATE;i++)assert(l[i]==(float)(.25*sin(6.283185307179586*80*i/RATE)));
    p.eq_on=1;od_prepare(&c,&p,RATE);assert(!c.eq&&!c.sub);od_publish(1,&c);tone(80);
    assert(!od_process(1,l,r,RATE,RATE));assert(amplitude(40)<.00001);
    p.eq_on=0;
    p.sub_on=1;od_prepare(&c,&p,RATE);od_publish(0,&c);tone(80);run(0);assert(amplitude(40)>.008);assert(amplitude(80)>.20);
    tone(80);run(1);assert(amplitude(40)<.00001);
    p.sub_on=0;p.eq_on=1;p.bands[5][2]=-6;od_prepare(&c,&p,RATE);od_publish(2,&c);tone(3000);run(2);assert(amplitude(3000)<.14);
    p.hp=90;od_prepare(&c,&p,RATE);od_publish(3,&c);tone(30);run(3);assert(amplitude(30)<.005);
    p.hp=0;p.eq_on=0;p.sub_on=1;p.wet=100;p.maxhz=80;p.minhz=25;
    od_prepare(&c,&p,RATE);od_publish(0,&c);tone(140);run(0);assert(amplitude(70)>.004);
    tone(1000);run(0);assert(amplitude(500)<.001);
    p.minhz=15;p.maxhz=30;od_prepare(&c,&p,RATE);od_publish(1,&c);tone(40);run(1);assert(amplitude(20)>.008);
    tone(80);run(1);assert(amplitude(40)<.005);
    p.low=p.high=0;od_prepare(&c,&p,RATE);assert(!c.sub);
    od_poll("/nonexistent",RATE);puts("output DSP tests passed");return 0;
}
