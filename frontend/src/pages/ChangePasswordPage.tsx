import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/ui/password-input";
import { RefreshCw, AlertCircle, CheckCircle2 } from "lucide-react";

export function ChangePasswordPage() {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const nav = useNavigate();

  const passwordMismatch = newPassword && confirmPassword && newPassword !== confirmPassword;
  const isValid = oldPassword && newPassword && confirmPassword && !passwordMismatch;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const newErrors: Record<string, string> = {};

    if (!oldPassword) newErrors.oldPassword = "Current password is required";
    if (!newPassword) newErrors.newPassword = "New password is required";
    if (!confirmPassword) newErrors.confirmPassword = "Confirm password is required";
    if (newPassword && confirmPassword && newPassword !== confirmPassword) {
      newErrors.confirmPassword = "Passwords do not match";
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    setErrors({});
    setSubmitting(true);

    try {
      await api.changePassword(oldPassword, newPassword);
      toast.success("Password changed successfully!", {
        icon: <CheckCircle2 className="h-5 w-5 text-success" />,
      });
      nav("/");
    } catch (e) {
      const error = e as ApiError;
      if (error.status === 401) {
        setErrors({ oldPassword: "Current password is incorrect" });
        toast.error("Current password is incorrect");
      } else if (error.status === 422) {
        // Policy violation—surface the server message verbatim
        toast.error(error.message);
        setErrors({ newPassword: error.message });
      } else {
        toast.error(error.message || "Failed to change password");
        setErrors({ form: error.message || "An error occurred" });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen md:grid-cols-[3fr_2fr]">
      {/* Brand panel (matching LoginPage aesthetic) */}
      <div className="hidden md:flex flex-col justify-center items-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 relative overflow-hidden">
        {/* Subtle animated gradient background */}
        <div className="absolute inset-0 opacity-20">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/30 rounded-full blur-3xl" />
          <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyan-500/20 rounded-full blur-3xl" />
        </div>
        <div className="relative text-center space-y-4 px-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-lg bg-white/10 backdrop-blur-sm border border-white/20">
            <RefreshCw className="h-8 w-8 text-white/80" />
          </div>
          <h2 className="text-3xl font-bold text-white">Refresh Access</h2>
          <p className="text-sm text-white/60 max-w-xs">
            Update your password to regain full access to your account
          </p>
        </div>
      </div>

      {/* Form panel */}
      <div className="styx-auth-form flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-2 text-center">
            <h1 className="text-2xl font-bold">Change Password</h1>
            <p className="text-sm text-muted-foreground">
              Enter your current password and choose a new one
            </p>
          </div>

          <form onSubmit={submit} className="space-y-4">
            {/* Current password */}
            <div className="space-y-2">
              <label htmlFor="old-password" className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Current Password
              </label>
              <PasswordInput
                id="old-password"
                placeholder="••••••••"
                value={oldPassword}
                onChange={(e) => {
                  setOldPassword(e.target.value);
                  setErrors((prev) => ({ ...prev, oldPassword: "" }));
                }}
                aria-invalid={errors.oldPassword ? true : undefined}
                aria-describedby={errors.oldPassword ? "old-password-error" : undefined}
                disabled={submitting}
              />
              {errors.oldPassword && (
                <p id="old-password-error" className="flex items-center gap-1.5 text-xs text-destructive">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                  {errors.oldPassword}
                </p>
              )}
            </div>

            {/* Divider */}
            <div className="relative py-2">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-background px-2 text-muted-foreground">New Password</span>
              </div>
            </div>

            {/* New password */}
            <div className="space-y-2">
              <label htmlFor="new-password" className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                New Password
              </label>
              <PasswordInput
                id="new-password"
                placeholder="••••••••"
                value={newPassword}
                onChange={(e) => {
                  setNewPassword(e.target.value);
                  setErrors((prev) => ({ ...prev, newPassword: "" }));
                }}
                aria-invalid={errors.newPassword ? true : undefined}
                aria-describedby={errors.newPassword ? "new-password-error" : undefined}
                disabled={submitting}
              />
              {errors.newPassword && (
                <p id="new-password-error" className="flex items-center gap-1.5 text-xs text-destructive">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                  {errors.newPassword}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Use a strong password with a mix of letters, numbers, and symbols
              </p>
            </div>

            {/* Confirm password */}
            <div className="space-y-2">
              <label htmlFor="confirm-password" className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Confirm Password
              </label>
              <PasswordInput
                id="confirm-password"
                placeholder="••••••••"
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  setErrors((prev) => ({ ...prev, confirmPassword: "" }));
                }}
                aria-invalid={passwordMismatch || errors.confirmPassword ? true : undefined}
                aria-describedby={errors.confirmPassword ? "confirm-password-error" : undefined}
                disabled={submitting}
              />
              {errors.confirmPassword && (
                <p id="confirm-password-error" className="flex items-center gap-1.5 text-xs text-destructive">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                  {errors.confirmPassword}
                </p>
              )}
            </div>

            {/* Form-level error */}
            {errors.form && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3">
                <p className="text-xs text-destructive flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  {errors.form}
                </p>
              </div>
            )}

            {/* Submit button */}
            <Button
              type="submit"
              className="w-full"
              size="default"
              disabled={submitting || !isValid}
            >
              {submitting ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Updating…
                </>
              ) : (
                "Update Password"
              )}
            </Button>
          </form>

          {/* Security note */}
          <div className="rounded-md border border-border/50 bg-muted/30 p-3">
            <p className="text-xs text-muted-foreground text-center">
              Your session will refresh automatically after updating your password
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
