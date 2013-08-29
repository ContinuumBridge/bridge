/*
 Create an upstream or downstream channel between an app.
 Upstream means between app and device.
 Downstream means between app and aggregator.
*/

#include <stdio.h>
#include <stdlib.h>
#include "CB_commslib.h"

int main(int argc, char *argv[])
{
    if (argc < 3) {
        printf("Usage: %s server_descriptor client_descriptor <isdownstream>\n", argv[0]);
        exit(1);
    }

    char *readerdesc;
    char *writerdesc;
    int readerid;
    int writerid;

    if (argc == 4) {
        // Downstream
        readerdesc = argv[1];
        writerdesc = argv[2];
        readerid = openChannel(readerdesc);
        writerid = openChannel(writerdesc);
        initServerChannel(readerid);
        initClientChannel(writerid);
    } else {
        // Upstream
        readerdesc = argv[2];
        writerdesc = argv[1];
        readerid = openChannel(readerdesc);
        writerid = openChannel(writerdesc);
        initClientChannel(readerid);
        initServerChannel(writerid);
    }

    for (int i = 0; ; ++i) {
        readChannel(readerid);
        printf("Data %s->%s [%s]\n", readerdesc, writerdesc, getChannelData(readerid));
        setChannelData(writerid, getChannelData(readerid));
        writeChannel(writerid);
        fflush(stdout);
    }

    closeChannel(readerid);
    closeChannel(writerid);

    return 0;
}
