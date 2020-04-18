/*
 * hello.c - Simple hello program
 */
#include <stdio.h>
#include <libhello.h>

int main(int argc, char *argv[])
{
  const char *person = NULL;

  if (argc > 1)
    person = argv[1];

  if (person)
    hello(person);
  else
    hello("stranger");

  return 0;
}
