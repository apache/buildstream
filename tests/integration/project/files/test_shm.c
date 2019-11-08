#include <errno.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>

int main ()
{
  int fd = shm_open ("/foo", O_RDONLY | O_CREAT, S_IRWXU);
  if (fd < 0)
  {
    fprintf (stderr, "Failed to open shm: %s\n", strerror (errno));
    exit(1);
  }

  int success = shm_unlink ("/foo");
  if  (success < 0)
  {
    fprintf (stderr, "Failed to close shm: %s\n", strerror (errno));
    exit(2);
  }

  close (fd);

  return 0;
}
