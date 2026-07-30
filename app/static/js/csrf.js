(function () {
  "use strict";

  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.getAttribute("content") : "";
  if (!token) return;

  window.cophyCsrfToken = token;

  const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

  function protectForm(form) {
    const method = (form.getAttribute("method") || "GET").toUpperCase();
    if (!unsafeMethods.has(method) || form.querySelector('input[name="csrf_token"]')) return;

    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "csrf_token";
    input.value = token;
    form.prepend(input);
  }

  function protectForms(root) {
    if (root instanceof HTMLFormElement) protectForm(root);
    if (root.querySelectorAll) root.querySelectorAll("form").forEach(protectForm);
  }

  protectForms(document);
  document.addEventListener("DOMContentLoaded", function () {
    protectForms(document);
  });

  new MutationObserver(function (mutations) {
    mutations.forEach(function (mutation) {
      mutation.addedNodes.forEach(function (node) {
        if (node.nodeType === Node.ELEMENT_NODE) protectForms(node);
      });
    });
  }).observe(document.documentElement, { childList: true, subtree: true });

  const nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const options = Object.assign({}, init || {});
    const requestMethod = options.method || (input instanceof Request ? input.method : "GET");
    const method = String(requestMethod).toUpperCase();
    const requestUrl = input instanceof Request ? input.url : input;
    const url = new URL(requestUrl, window.location.href);

    if (url.origin === window.location.origin && unsafeMethods.has(method)) {
      const headers = new Headers(input instanceof Request ? input.headers : undefined);
      new Headers(options.headers || {}).forEach(function (value, key) {
        headers.set(key, value);
      });
      headers.set("X-CSRFToken", token);
      headers.set("X-Requested-With", "XMLHttpRequest");
      options.headers = headers;
    }

    return nativeFetch(input, options);
  };
})();
