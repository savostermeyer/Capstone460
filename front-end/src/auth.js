export function getCurrentUser() {
  try {
    const user = localStorage.getItem("skinai_user");
    return user && user.trim() ? user.trim() : null;
  } catch {
    return null;
  }
}

export function isAuthenticated() {
  return Boolean(getCurrentUser());
}
