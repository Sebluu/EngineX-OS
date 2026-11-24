#define _GNU_SOURCE
#include "output_dsp.h"
#include <pthread.h>
#include <assert.h>

static void *publish(void *unused) {
    (void)unused;
    struct od_params p={0};p.eq_on=p.sub_on=1;p.wet=25;p.maxhz=56;p.minhz=25;p.low=p.high=100;p.threshold=-48;p.attack=12;p.release=100;
    for(int b=0;b<8;b++){p.bands[b][0]=90*(b+1);p.bands[b][1]=.707f;}
    for(int i=0;i<12000;i++) {
        p.bands[5][2]=(float)(i%25)-12;
        struct od_cfg c;od_prepare(&c,&p,48000);
        for(unsigned pair=0;pair<OD_PAIRS;pair++)od_publish(pair,&c);
    }
    return NULL;
}
int main(void) {
    pthread_t worker;assert(!pthread_create(&worker,NULL,publish,NULL));
    for(int n=0;n<12000;n++)for(unsigned p=0;p<OD_PAIRS;p++) {
        float l[64],r[64];for(unsigned i=0;i<64;i++)l[i]=r[i]=.1f;
        od_process(p,l,r,64,48000);
        for(unsigned i=0;i<64;i++)assert(isfinite(l[i])&&isfinite(r[i]));
    }
    assert(!pthread_join(worker,NULL));
    od_poll("/nonexistent",48000,0);
    puts("output DSP concurrent publisher tests passed");return 0;
}
