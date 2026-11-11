#include <unistd.h>
#include <stdio.h>

void do_greeting() {
	__uid_t uid;
	uid = getuid();
	printf("Hello, %d, nice to meet you! \n", uid);
}

int main() {
	do_greeting();
}
