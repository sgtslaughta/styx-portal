/* LD_PRELOAD shim: make mutter think it is not in a systemd user unit, so it
 * starts Xwayland eagerly (MANDATORY policy) instead of on demand. */
#include <errno.h>
#include <stdlib.h>

int sd_pid_get_user_unit(int pid, char **unit)
{
    (void)pid;
    (void)unit;
    return -ENODATA;
}

__attribute__((constructor)) static void xwl_eager_init(void)
{
    unsetenv("LD_PRELOAD");   /* do not leak into apps the shell launches */
}
