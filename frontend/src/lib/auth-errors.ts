/** Map backend auth error messages (HTTPException detail) to friendly copy. */
const LOGIN_ERRORS: Record<string, string> = {
  "Invalid credentials": "Email or password is incorrect.",
  "User inactive": "This account is disabled. Contact an administrator.",
  "Too many requests": "Too many attempts. Wait a minute and try again.",
};

export function friendlyLoginError(message: string): string {
  return LOGIN_ERRORS[message] ?? message;
}
