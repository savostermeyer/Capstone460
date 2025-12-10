// scripts/app.js

(function () {
  // footer year
  const y = document.getElementById('year');
  if (y) y.textContent = new Date().getFullYear();

  // active nav link
  const file = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav .nav-link[data-page]').forEach(a => {
    if (a.getAttribute('data-page') === file) a.classList.add('active');
  });

  // flip Login -> Account if signed in (optional future account page)
  try {
    const user = localStorage.getItem('skinai_user') || sessionStorage.getItem('skinai_user');
    const loginLink = document.querySelector('.js-login-link');
    if (loginLink && user) {
      loginLink.textContent = 'Account';
      loginLink.setAttribute('href', 'account.html');
    }
  } catch {}
})();