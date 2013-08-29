#include <stdio.h>
#include <stdlib.h>
#include <libgen.h>
#include <unistd.h>
#include "CB_commslib.h"

int main(int argc, char *argv[])
{
    if (argc != 2)
    {
        printf("Usage: %s server_descriptor\n", argv[0]);
        exit(1);
    }

    int chid = openChannel(argv[1]);
    initServerChannel(chid);

    char buffer[1024];
    for (size_t i = 0; ; ++i)
    {
        snprintf(buffer, 1023, "Data value from %s: %zu", argv[1], i);
        printf("Device sent data to %s [%s]\n",
               getChannelName(chid),
               buffer);
        setChannelData(chid, buffer);
        writeChannel(chid);
        sleep(1);
    }

    closeChannel(chid);

    return 0;
}
