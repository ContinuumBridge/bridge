/* Create a channel between somewhere and an app. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/un.h> /* Unix domain sockets */

const ssize_t c_buffersize = 1024;
const ssize_t c_namesize = 1024;
char g_dir[c_namesize];
char g_name[c_namesize];
int g_sockfd;
int g_connectionfd;

void cleanUp(void)
{
  printf("Start cleanup\n");
  printf("Cleanup complete\n");
}

void error(const char *msg)
{
    perror(msg);
    exit(1);
}

void makeDir()
{
  if (mkdir(g_dir, 0700) != 0)
  {
    /* Check that it already existed, otherwise a flag real error. */
    if (errno != EEXIST)
      error("Creating app directory");
  }
}

void makeChannel()
{
  socklen_t clilen;
  struct sockaddr_un serv_addr, cli_addr;
  int backlog = 5;

  g_sockfd = socket(AF_LOCAL, SOCK_STREAM, 0);
  if (g_sockfd < 0)
    error("Opening socket");
  unlink(g_name);
  bzero((char *) &serv_addr, sizeof(serv_addr));

  serv_addr.sun_family = AF_LOCAL;
  strcpy(serv_addr.sun_path, g_name);

  if (bind(g_sockfd, (struct sockaddr *) &serv_addr, sizeof(serv_addr)) < 0)
    error("On binding");
  listen(g_sockfd, backlog);
  clilen = sizeof(cli_addr);
  g_connectionfd = accept(g_sockfd,
                          (struct sockaddr *) &cli_addr,
                          &clilen);
  if (g_connectionfd < 0)
    error("On accept");
}

void runChannel()
{
  char buffer[c_buffersize];

  while (1)
  {
    bzero(buffer, c_buffersize - 1);
    if (read(g_connectionfd, buffer, c_buffersize - 1) < 0)
      error("Reading from socket");

    printf("Here is the message: %s\n", buffer);
    if (write(g_connectionfd, "I got your message", 18) < 0)
      error("Writing to socket");
  }

  close(g_connectionfd);
  close(g_sockfd);
}

int main(int argc, char *argv[])
{
  /* Command line: createChannel appname socketname */
  if (argc != 3)
  {
    printf("Usage: %s appname socketname\n", argv[0]);
    exit(1);
  }

  atexit(&cleanUp);

  strcpy(g_dir, "/lxc/");
  strncat(g_dir, argv[1], c_namesize - 1);
  strcpy(g_name, g_dir);
  strncat(g_name, "/", c_namesize - 1);
  strncat(g_name, argv[2], c_namesize - 1);
  makeDir();
  makeChannel();
  runChannel();
  return 0;
}
