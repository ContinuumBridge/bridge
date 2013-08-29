#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libgen.h>
#include <unistd.h>

#include "CB_commslib.h"

int main(int argc, char *argv[])
{
    CB_ls("/lxc", "");
    CB_ls("/lxc", basename(argv[0]));

    // Sockets are named in/out as seen by the app
    size_t nchannels = openAppChannels(basename(argv[0]));
    for (size_t ch = 0; ch < nchannels; ++ch)
        initClientChannel(ch);

    char buffer[1024];
    while (1)
    {
        for (size_t ch = 0; ch < nchannels; ++ch)
            if (isInputChannel(ch))
            {
                readChannel(ch);
                printf("App received data from %s [%s]\n",
                       getChannelName(ch),
                       getChannelData(ch));
                strncpy(buffer, getChannelData(ch), 1023);
            }

        for (size_t ch = 0; ch < nchannels; ++ch)
            if (isOutputChannel(ch))
            {
                printf("App sent data to %s [%s]\n",
                       getChannelName(ch),
                       buffer);
                setChannelData(ch, buffer);
                writeChannel(ch);
            }
        sleep(1);
    }

    for (size_t ch = 0; ch < nchannels; ++ch)
        closeChannel(ch);

    return 0;
}
