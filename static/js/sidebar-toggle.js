/**
 * Sidebar Toggle Functionality
 * Handles collapsible sidebar with localStorage persistence
 */
document.addEventListener('DOMContentLoaded', function() {
  const body = document.body;
  const toggle = document.getElementById('sidebar-toggle');

  // Load saved state from localStorage
  if (localStorage.getItem('sidebar-collapsed') === 'true') {
    body.classList.add('sidebar-collapsed');
  }

  // Toggle sidebar and save state
  if (toggle) {
    toggle.addEventListener('click', function() {
      body.classList.toggle('sidebar-collapsed');
      localStorage.setItem('sidebar-collapsed', body.classList.contains('sidebar-collapsed'));
    });
  }
});
