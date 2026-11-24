/* Signal contracts for the experimental insert, not a deck latency certificate.
 * Build with both OD_FEATURE_EQ and OD_FEATURE_SUB enabled. */
#define _GNU_SOURCE
#include "output_dsp.h"
#include <assert.h>

enum { RATE = 96000, COUNT = 24577 };
static float reference[2][COUNT], partitioned[2][COUNT], dry[2][COUNT];

static struct od_params parameters(void) {
    struct od_params p = {0};
    p.wet=25; p.maxhz=56; p.minhz=25; p.low=p.high=100;
    p.threshold=-48; p.attack=12; p.release=100;
    const float hz[] = {90,180,350,750,1500,3000,8000,19000};
    for (unsigned i=0;i<8;i++) { p.bands[i][0]=hz[i]; p.bands[i][1]=.707f; }
    return p;
}

static void publish(unsigned pair, const struct od_params *p, unsigned rate) {
    struct od_cfg c;
    assert(od_valid(p));
    od_prepare(&c,p,rate);
    od_publish(pair,&c);
}

static void inactive_is_bit_exact(void) {
    /* Include signed zero and subnormals: floating-point equality is insufficient. */
    static const uint32_t words[] = {
        0x00000000,0x80000000,0x00000001,0x80000001,
        0x3f000000,0xbf000000,0x3f800000,0xbf800000
    };
    static const unsigned rates[] = {32000,44100,48000,88200,96000,192000};
    struct od_params p=parameters();
    p.eq_on=1; /* An enabled, flat EQ must also be an exact bypass. */
    for (unsigned rate=0;rate<sizeof rates/sizeof *rates;rate++) {
        float l[8],r[8];
        memcpy(l,words,sizeof l); memcpy(r,words,sizeof r);
        publish(0,&p,rates[rate]);
        assert(!od_process(0,l,r,8,rates[rate]));
        assert(!memcmp(l,words,sizeof l) && !memcmp(r,words,sizeof r));
    }
}

static void block_cuts_do_not_change_audio(void) {
    struct od_params p=parameters(); p.eq_on=p.sub_on=1;
    p.hp=25; p.bands[5][2]=-6; p.bands[7][2]=3;
    for (unsigned i=0;i<COUNT;i++) {
        double t=6.283185307179586*i/RATE;
        dry[0][i]=(float)(.12*sin(80*t)+.03*sin(3000*t)+.01*sin(19000*t));
        dry[1][i]=(float)(.09*sin(140*t)-.02*sin(3000*t));
    }
    memcpy(reference,dry,sizeof dry); memcpy(partitioned,dry,sizeof dry);
    publish(0,&p,RATE); publish(1,&p,RATE);
    /* Reference: one frame per call, including the enable crossfade. */
    for (unsigned i=0;i<COUNT;i++)
        assert(od_process(0,reference[0]+i,reference[1]+i,1,RATE));
    const unsigned cuts[]={225,1,64,511,17,1024,63};
    for (unsigned i=0,cut=0;i<COUNT;cut++) {
        unsigned n=cuts[cut%(sizeof cuts/sizeof *cuts)];
        if (n>COUNT-i) n=COUNT-i;
        assert(od_process(1,partitioned[0]+i,partitioned[1]+i,n,RATE));
        i+=n;
    }
    assert(!memcmp(reference,partitioned,sizeof reference));
    double added=0;
    for (unsigned i=0;i<COUNT;i++) {
        assert(isfinite(reference[0][i]) && isfinite(reference[1][i]));
        added+=fabs((double)reference[0][i]-dry[0][i]);
    }
    assert(added>1); /* A bypassed implementation cannot satisfy this test. */
}

static void immediate_impulse_and_disable(void) {
    struct od_params p=parameters(); p.eq_on=1; p.bands[5][2]=-6;
    publish(2,&p,RATE);
    memset(reference,0,sizeof reference);
    /* Settle the initial control transition with silence. */
    assert(od_process(2,reference[0],reference[1],COUNT,RATE));
    reference[0][0]=.1f;
    assert(od_process(2,reference[0],reference[1],64,RATE));
    /* The existing sample is processed immediately: no extra queued audio block. */
    assert(fabsf(reference[0][0])>.001f);
    assert(fabsf(reference[0][1])>.000001f); /* The EQ really processed the impulse. */
    for (unsigned i=0;i<64;i++) assert(reference[1][i]==0);

    p.eq_on=0; publish(2,&p,RATE);
    for (unsigned i=0;i<COUNT;i++) { reference[0][i]=.125f; reference[1][i]=-.0625f; }
    assert(od_process(2,reference[0],reference[1],COUNT,RATE));
    for (unsigned i=0;i<COUNT;i++)
        assert(isfinite(reference[0][i]) && isfinite(reference[1][i]));
    float l[]={0.0f,-0.0f,.25f,-.125f},r[]={-.25f,.125f,-0.0f,0.0f};
    float before_l[4],before_r[4];
    memcpy(before_l,l,sizeof l); memcpy(before_r,r,sizeof r);
    assert(!od_process(2,l,r,4,RATE));
    assert(!memcmp(l,before_l,sizeof l) && !memcmp(r,before_r,sizeof r));
    /* Processing other outputs must not activate the remaining output. */
    assert(!od_process(3,l,r,4,RATE));
    assert(!memcmp(l,before_l,sizeof l) && !memcmp(r,before_r,sizeof r));
}

int main(void) {
    assert(OD_FEATURE_EQ && OD_FEATURE_SUB);
    inactive_is_bit_exact();
    block_cuts_do_not_change_audio();
    immediate_impulse_and_disable();
    od_poll("/nonexistent",RATE,0);
    puts("output DSP continuity: bit-exact bypass, block independence, immediate impulse, disable and output isolation passed");
    return 0;
}
