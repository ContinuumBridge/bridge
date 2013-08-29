/* This is the link between then outside world and all of the apps in
 * the system.
 */

#include <stdio.h>

void commandloop(void)
{
  while(1)
  {
    printf("Command:\r");
    switch (cmd)
    {
    case 'l':
      listApps();
      break;
    case 'c':
      createApp();
      break;
    default:
      printf("Unknown command\n");
      break;
    }
  }
}

int main()
{
  commandloop();
  return 0;
}
