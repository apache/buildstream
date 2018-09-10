#include <stdio.h>
int main()
{
   // printf() displays the string inside quotation
#ifdef FULL_PROJECT
   printf("Hello, World! Built from the source root.\n");
#else
   printf("Hello, World! Built from a subdirectory of the source.\n");
#endif   
   return 0;
}
