document.addEventListener("DOMContentLoaded", () => {
  const menuButton = document.querySelector(".mobile-menu-toggle");
  const nav = document.querySelector(".main-nav");

  if (menuButton && nav) {
    menuButton.addEventListener("click", () => {
      const expanded = menuButton.getAttribute("aria-expanded") === "true";
      menuButton.setAttribute("aria-expanded", String(!expanded));
      nav.classList.toggle("nav-open", !expanded);
      menuButton.textContent = expanded ? "☰" : "×";
    });
  }

  document.querySelectorAll(".toast-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".toast")?.remove());
  });
  document.querySelectorAll(".toast").forEach((toast) => {
    window.setTimeout(() => {
      toast.classList.add("toast-leaving");
      window.setTimeout(() => toast.remove(), 350);
    }, 5200);
  });

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  document.querySelectorAll(".event-card-image img, .detail-hero img, .auth-art img").forEach((image) => {
    image.addEventListener("error", () => {
      image.closest(".event-card-image, .detail-hero, .auth-art")?.classList.add("image-unavailable");
      image.remove();
    }, { once: true });
  });

  const revealTargets = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries, currentObserver) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          currentObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    revealTargets.forEach((target) => observer.observe(target));
  } else {
    revealTargets.forEach((target) => target.classList.add("is-visible"));
  }
});
