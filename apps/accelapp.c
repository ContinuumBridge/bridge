#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libgen.h>
#include <unistd.h>
#include <time.h>

#include "CB_commslib.h"

#define BUFFER_LEN 128

char data[1024];
char outData[1024];
long int accel[3];
long int xValues[BUFFER_LEN],
         yValues[BUFFER_LEN],
         zValues[BUFFER_LEN];
int Loc = 0;
int xTotal, yTotal, zTotal;
float xAverage = 0.0;
float yAverage = 0.0;
float zAverage = 0.0;
int learnt = 0;

static void
getAccel(size_t ch)
{
    const char *cmd = "accel";
    char * pEnd;
    setChannelData(ch, cmd);
    writeChannel(ch);
    readChannel(ch);
    //snprintf(data, 1023, "%s:%s", cmd, getChannelData(ch));
    snprintf(data, 1023, "%s", getChannelData(ch));
    accel[0] = strtol (data,&pEnd,0);
    accel[1] = strtol (pEnd,&pEnd,0);
    accel[2] = strtol (pEnd,NULL,0);
}

int main(int argc, char *argv[])
{
    CB_ls("/lxc", "");
    CB_ls("/lxc", basename(argv[0]));

    // Assumes one input, one output
    size_t nchannels = openAppChannels(basename(argv[0]));
    size_t inchan = nchannels + 1;
    size_t outchan = nchannels + 1;
    for (size_t ch = 0; ch < nchannels; ++ch) {
        if (isInputChannel(ch)) {
            if (inchan != (nchannels + 1)) {
                fprintf(stderr, "Input channel already set\n");
                goto close;
            }
            inchan = ch;
        }
        if (isOutputChannel(ch)) {
            if (outchan != (nchannels + 1)) {
                fprintf(stderr, "Output channel already set\n");
                goto close;
            }
            outchan = ch;
        }
        initClientChannel(ch);
    }

    while (1)
    {
        getAccel(inchan);
        //printf ("App data: %ld, %ld, %ld\n", accel[0], accel[1], accel[2]); 
        xTotal = xTotal - xValues[Loc] + accel[0];
        yTotal = yTotal - yValues[Loc] + accel[1];
        zTotal = zTotal - zValues[Loc] + accel[2];
        xValues[Loc] = accel[0];
        yValues[Loc] = accel[1];
	zValues[Loc] = accel[2];
        Loc = (Loc + 1)%BUFFER_LEN;
        xAverage = xTotal/BUFFER_LEN; 
        yAverage = yTotal/BUFFER_LEN; 
        zAverage = zTotal/BUFFER_LEN; 
        printf("Loc = %d\n", Loc);
        //printf("xAv = %f, yAv = %f, zAv = %f\n", xAverage, yAverage, zAverage);
    	//snprintf(outData, 1023, "%f %f %f", xAverage, yAverage, zAverage);

        if (learnt) {
            if ((abs(accel[0]-xAverage) > 2) ||
               (abs(accel[1]-yAverage) > 2) ||
               (abs(accel[2]-zAverage) > 2)) { 
                    printf ("Vibration event\n");
    	            snprintf(outData, 1023, "%s %d", "Vibration event", Loc); 
                    //printf("App sent data to %s [%s]\n",
                    //   getChannelName(outchan),
                    //   outData);
                    setChannelData(outchan, outData);
                    writeChannel(outchan);
            }
        }
        if (Loc > 126)
            learnt = 1;  
        //nanosleep(10000000);
    }

close:
    for (size_t ch = 0; ch < nchannels; ++ch)
        closeChannel(ch);

    return 0;
}
