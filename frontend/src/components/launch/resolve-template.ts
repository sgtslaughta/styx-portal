import { api } from "@/api/client";
import type { ServiceTemplate, TemplateCreate } from "@/lib/types";

export const repoOf = (image: string) => image.split("@")[0]!.replace(/:[^:/]*$/, "");

/** True when the template's image (any registry prefix or tag) is the LinuxServer image `regName`. */
export const isLinuxserverImage = (image: string, regName: string) =>
  [`lscr.io/linuxserver/${regName}`, `linuxserver/${regName}`].includes(repoOf(image));

/** Same-repo template that is the user's own or shared (no owner) can be reused. */
function reusable(t: ServiceTemplate, regName: string | undefined, userId: string | undefined) {
  if (!regName) return false;
  const sameRepo = isLinuxserverImage(t.image, regName);
  return sameRepo && (t.owner_id == null || t.owner_id === userId);
}

interface Opts {
  template?: ServiceTemplate | null;
  data: TemplateCreate;
  create: (d: TemplateCreate) => Promise<ServiceTemplate>;
  regName?: string;
  userId?: string;
  isAdmin: boolean;
}

/** Launching never overwrites a saved setup; a new image gets a template, or reuses a same-named one. */
export async function resolveTemplate({ template, data, create, regName, userId, isAdmin }: Opts): Promise<ServiceTemplate> {
  if (template) return template;
  try {
    return await create(data);
  } catch {
    const found = (await api.listTemplates()).find((t) => t.name === data.name);
    const ok = found && (regName ? reusable(found, regName, userId) : found.owner_id == null ? isAdmin : found.owner_id === userId);
    if (!found || !ok) throw new Error(`A template named “${data.display_name}” already exists with a different image or owner — choose another name`);
    if (found.owner_id === userId) {
      const { cpu_limit, memory_limit, gpu_enabled, gpu_count } = data;
      return api.updateTemplate(found.id, { cpu_limit, memory_limit, gpu_enabled, gpu_count });
    }
    return found;
  }
}
