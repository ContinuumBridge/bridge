#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(void)
{
  int t = 0;
  FILE *logf = NULL;
  if (!(logf = fopen("./count.log", "w")))
  {
    fprintf(stderr, "Error opening file\n");
    exit(1);
  }
  while(1)
  {
    printf("Count:%d\n", t);
    fprintf(logf, "Count:%d\n", t);
    fflush(logf);
    sleep(1);
    ++t;
  }
  return 0;
}
