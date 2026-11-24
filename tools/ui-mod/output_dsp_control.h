#ifndef SC_OUTPUT_DSP_CONTROL_H
#define SC_OUTPUT_DSP_CONTROL_H
/* Control-worker only. Nothing here runs on an audio/render thread. */
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <stdlib.h>
#include "output_dsp.h"

static int od_read_small(const char *path,char *buf,size_t capacity) {
    int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);
    if(fd<0)return 0;
    struct stat st;
    int ok=fstat(fd,&st)==0 && S_ISREG(st.st_mode) && st.st_size>0 && (size_t)st.st_size<capacity;
    ssize_t n=ok?read(fd,buf,capacity-1):-1;
    close(fd);
    if(n<=0 || n!=st.st_size)return 0;
    buf[n]=0;return 1;
}
static int od_record(const char *path,const char *boot,double now,unsigned *mask,unsigned *rate) {
    char buf[160],id[37],extra;double then;unsigned m,r;
    if(!od_read_small(path,buf,sizeof buf) ||
       sscanf(buf,"OD1 %36s %lf %u %u %c",id,&then,&m,&r,&extra)!=4 ||
       strcmp(boot,id) || !isfinite(then) || then<0 || now<then || now-then>3 || m>3)return 0;
    *mask=m;*rate=r;return 1;
}
static unsigned od_control_poll(const char *directory,unsigned rate) {
    static char boot[37];static double last_ready=-10;
    char path[4096],text[160],id[64];struct timespec t;
    if(!boot[0]) {
        if(!od_read_small("/proc/sys/kernel/random/boot_id",id,sizeof id) || strlen(id)!=37)return 0;
        memcpy(boot,id,36);boot[36]=0;
    }
    if(clock_gettime(CLOCK_BOOTTIME,&t))return 0;
    double now=t.tv_sec+t.tv_nsec*1e-9;
    unsigned features=(OD_FEATURE_EQ?1u:0u)|(OD_FEATURE_SUB?2u:0u),mask=0,unused=0;
    if(rate<32000 || rate>192000)features=0;
    if(snprintf(path,sizeof path,"%s/backend.lease",directory)>=(int)sizeof path)return 0;
    if(!od_record(path,boot,now,&mask,&unused))mask=0;
    /* A fresh native heartbeat proves that this Engine actually loaded the core.
       It cannot enable processing: only the backend's independently checked lease can. */
    if(now-last_ready>=.5) {
        char temp[4096];last_ready=now;
        if(snprintf(path,sizeof path,"%s/core.ready",directory)>=(int)sizeof path ||
           snprintf(temp,sizeof temp,"%s/.core-%ld",directory,(long)getpid())>=(int)sizeof temp)return 0;
        if(!mkdir(directory,0700) || errno==EEXIST) {
            int n=snprintf(text,sizeof text,"OD1 %s %.3f %u %u\n",boot,now-.02,features,rate);
            int fd=open(temp,O_CREAT|O_TRUNC|O_WRONLY|O_NOFOLLOW|O_NONBLOCK,0600);
            if(fd>=0){ssize_t written=write(fd,text,(size_t)n);int closed=close(fd);if(written==n&&!closed)rename(temp,path);unlink(temp);}
        }
    }
    return mask&features;
}
#endif
