document.addEventListener('DOMContentLoaded', function () {
  const yearEl = document.querySelector('[data-copyright-year]');
  if (!yearEl) return;

  const currentYear = new Date().getFullYear();
  const startYear = 2026;
  yearEl.textContent = startYear === currentYear ? String(startYear) : `${startYear}–${currentYear}`;
});
