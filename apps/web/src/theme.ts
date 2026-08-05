export type ThemePreference = "light" | "dark" | "system";

const storageKey = "energy-manager-theme";
const media = window.matchMedia("(prefers-color-scheme: dark)");

function resolvedTheme(preference: ThemePreference): "light" | "dark" {
  return preference === "system"
    ? media.matches
      ? "dark"
      : "light"
    : preference;
}

export function applyTheme(preference: ThemePreference, persist = true) {
  const safePreference: ThemePreference = ["light", "dark", "system"].includes(
    preference,
  )
    ? preference
    : "system";
  const root = document.documentElement;
  root.dataset.themePreference = safePreference;
  root.dataset.theme = resolvedTheme(safePreference);
  root.style.colorScheme = root.dataset.theme;
  if (persist) localStorage.setItem(storageKey, safePreference);
}

export function initializeTheme() {
  applyTheme(
    (localStorage.getItem(storageKey) as ThemePreference) || "system",
    false,
  );
}

media.addEventListener("change", () => {
  const preference = (document.documentElement.dataset.themePreference ||
    "system") as ThemePreference;
  if (preference === "system") applyTheme("system", false);
});
