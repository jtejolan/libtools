const updateHomepageAccountLink = async () => {
  try {
    const response = await fetch("/auth/me", { cache: "no-store" });
    if (!response.ok) return;
    const link = document.querySelector("#home-account-link");
    link.href = "/dashboard";
    link.innerHTML = 'Dashboard <span aria-hidden="true">→</span>';
  } catch {
    // Keep the public login link when session status cannot be checked.
  }
};

updateHomepageAccountLink();

const bookQuotes = window.bookQuotes || [];

const quoteFade = document.querySelector("#quote-fade");
const quoteTextEl = document.querySelector("#book-quote-text");
const quoteTitleEl = document.querySelector("#book-quote-title");
const quoteAuthorEl = document.querySelector("#book-quote-author");

const QUOTE_INTERVAL_MS = 10000;
const QUOTE_FADE_MS = 500;

let currentQuoteIndex = Math.floor(Math.random() * bookQuotes.length);

function pickNextQuoteIndex() {
  if (bookQuotes.length < 2) return currentQuoteIndex;
  let nextIndex;
  do {
    nextIndex = Math.floor(Math.random() * bookQuotes.length);
  } while (nextIndex === currentQuoteIndex);
  return nextIndex;
}

function renderQuote(index) {
  const quote = bookQuotes[index];
  quoteTextEl.textContent = quote.quote;
  quoteTitleEl.textContent = quote.title;
  quoteAuthorEl.textContent = quote.author;
}

function showNextQuote() {
  currentQuoteIndex = pickNextQuoteIndex();

  if (!quoteFade) {
    renderQuote(currentQuoteIndex);
    return;
  }

  quoteFade.classList.add("is-swapping");
  window.setTimeout(() => {
    renderQuote(currentQuoteIndex);
    quoteFade.classList.remove("is-swapping");
  }, QUOTE_FADE_MS);
}

renderQuote(currentQuoteIndex);

if (bookQuotes.length > 1) {
  window.setInterval(showNextQuote, QUOTE_INTERVAL_MS);
}

if ("IntersectionObserver" in window) {
  const revealTargets = document.querySelectorAll(
    ".hero-copy, .hero-identity, .section-heading, .tool-card, .manifesto"
  );

  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15, rootMargin: "0px 0px -60px 0px" }
  );

  revealTargets.forEach((el) => {
    el.classList.add("reveal");
    revealObserver.observe(el);
  });

  document.querySelector(".hero-copy").style.transitionDelay = "120ms";
  document
    .querySelectorAll(".tool-card")
    .forEach((el, i) => (el.style.transitionDelay = `${i * 90}ms`));
}

fetch("/api/public/stats")
  .then((res) => (res.ok ? res.json() : null))
  .then((stats) => {
    if (!stats) return;
    const itemsEl = document.querySelector("#lendery-stat-count");
    if (itemsEl && typeof stats.lendery_items === "number") {
      itemsEl.textContent = stats.lendery_items.toLocaleString();
    }
    const clubsEl = document.querySelector("#bookclub-stat-count");
    if (clubsEl && typeof stats.bookclub_clubs === "number") {
      clubsEl.textContent = stats.bookclub_clubs.toLocaleString();
    }
  })
  .catch(() => {});

const prefersReducedMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)"
).matches;
const supportsFinePointer = window.matchMedia("(pointer: fine)").matches;

if (!prefersReducedMotion && supportsFinePointer) {
  const maxTilt = 6;

  document.querySelectorAll(".lendery-card, .bookclub-card").forEach((card) => {
    card.addEventListener("mousemove", (event) => {
      const rect = card.getBoundingClientRect();
      const px = (event.clientX - rect.left) / rect.width;
      const py = (event.clientY - rect.top) / rect.height;
      const rotateY = (px - 0.5) * maxTilt * 2;
      const rotateX = (0.5 - py) * maxTilt * 2;
      card.style.setProperty("--tilt-x", `${rotateX}deg`);
      card.style.setProperty("--tilt-y", `${rotateY}deg`);
    });

    card.addEventListener("mouseleave", () => {
      card.style.setProperty("--tilt-x", "0deg");
      card.style.setProperty("--tilt-y", "0deg");
    });
  });
}
