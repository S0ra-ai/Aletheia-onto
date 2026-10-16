/**
 * Where the console is mounted, and how to build a URL that survives a full page load.
 *
 * Vite serves the app at `/` during development; the production image mount is `/admin`,
 * beside the API on the same origin. So the *router* path and the *address bar* path differ
 * by that prefix in production and match in development, and anything that navigates without
 * going through the router has to add it back.
 *
 * This is its own module because getting it wrong is invisible in development and shows up in
 * production as a raw JSON page: `window.location.assign('/login')` asked the server for a
 * path the SPA is not mounted at, and the server answered the auth middleware's
 * `{"detail":"缺少访问令牌"}` instead of the login form. Every 401 landed there -- an expired
 * session ended on a page of JSON.
 */

export const ROUTER_BASENAME = import.meta.env.PROD ? '/admin' : '/';

/**
 * An app path as the server sees it.
 *
 * `appHref('login')` is `/login` in development and `/admin/login` in production, which is
 * the difference between the login form and an error document.
 */
export const appHref = (path: string): string =>
  `${ROUTER_BASENAME.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
