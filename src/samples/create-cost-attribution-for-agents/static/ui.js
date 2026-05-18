function toggleDetails(){
  const cols = document.querySelectorAll('.details-col');
  const visible = cols.length>0 && cols[0].style.display !== 'table-cell';
  cols.forEach(c => c.style.display = visible ? 'table-cell' : 'none');
}

// Hide details columns by default on load
document.addEventListener('DOMContentLoaded', ()=>{
  const cols = document.querySelectorAll('.details-col');
  cols.forEach(c=> c.style.display='none');
});
