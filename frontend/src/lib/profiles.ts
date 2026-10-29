/** Where a template keeps its persistent profile: explicit mount, else the first volume. */
export function profileMountOf(
  profileMount: string | null | undefined,
  volumes: { mount: string }[] | null | undefined,
): string {
  return profileMount?.trim() || volumes?.[0]?.mount || "";
}
