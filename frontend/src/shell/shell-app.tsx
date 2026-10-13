/** Slug from /_styx/app/<slug>/... */
export function shellSlug(pathname: string): string {
  return pathname.replace(/^\/_styx\/app\//, "").split("/")[0] ?? "";
}

// Placeholder; replaced by the real shell UI.
export function ShellApp() {
  return <p>{shellSlug(location.pathname)}</p>;
}
