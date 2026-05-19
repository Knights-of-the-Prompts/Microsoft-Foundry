function toggleDetails(){
  const btn = document.getElementById('toggle-details');
  const cols = document.querySelectorAll('.details-col');
  const expanded = btn.getAttribute('aria-expanded') === 'true';
  const next = !expanded;
  btn.setAttribute('aria-expanded', String(next));
  btn.textContent = next ? 'Hide agent details' : 'Show agent details';
  cols.forEach(c => c.style.display = next ? '' : 'none');
}

// Hide details columns by default on load
document.addEventListener('DOMContentLoaded', ()=>{
  const btn = document.getElementById('toggle-details');
  if(btn) btn.setAttribute('aria-expanded','false');
  const cols = document.querySelectorAll('.details-col');
  cols.forEach(c=> c.style.display='none');
});
