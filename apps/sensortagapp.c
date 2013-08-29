#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libgen.h>
#include <unistd.h>

#include "CB_commslib.h"

char data[1024];

static void
getAmbientTemperature(size_t ch)
{
    const char *cmd = "ambtemp";
    setChannelData(ch, cmd);
    writeChannel(ch);
    readChannel(ch);
    snprintf(data, 1023, "%s:%s", cmd, getChannelData(ch));
}

static void
getObjectTemperature(size_t ch)
{
    const char *cmd = "objtemp";
    setChannelData(ch, cmd);
    writeChannel(ch);
    readChannel(ch);
    snprintf(data, 1023, "%s:%s", cmd, getChannelData(ch));
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
        getAmbientTemperature(inchan);
        printf("App sent data to %s [%s]\n",
               getChannelName(outchan),
               data);
        setChannelData(outchan, data);
        writeChannel(outchan);

        getObjectTemperature(inchan);
        printf("App sent data to %s [%s]\n",
               getChannelName(outchan),
               data);
        setChannelData(outchan, data);
        writeChannel(outchan);

        sleep(1);
    }

close:
    for (size_t ch = 0; ch < nchannels; ++ch)
        closeChannel(ch);

    return 0;
}
