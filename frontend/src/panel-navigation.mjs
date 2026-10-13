const staffOrder=['dashboard','members','payments','cards','reception','access','classes','stock','employees','notifications'];
const staffLabels={members:'Üye işlemleri',payments:'Ödeme al',cards:'RFID kart işlemleri',stock:'Hızlı satış',employees:'Mesailerim'};
export function panelPages(pages,user,permissions={}){
  if(!user)return [];
  return pages.filter(p=>p.roles.includes(user.role)||user.role==='admin'&&['cards','reception'].includes(p.id)).filter(p=>{
    if(user.role!=='staff')return true;
    if(p.id==='sensors')return false;
    const permission={members:'memberManagement',payments:'collections',cards:'cardManagement'}[p.id];
    if(p.id==='classes')return permissions.classBooking!==false||permissions.classAttendance!==false;
    if(p.id==='stock')return permissions.productSales!==false||permissions.productReturns===true;
    return !permission||permissions[permission]!==false;
  }).map(p=>({...p,label:user.role==='staff'?(staffLabels[p.id]||p.label):p.label,menu:!(user.role==='admin'&&['cards','reception'].includes(p.id)||user.role==='staff'&&p.id==='reports'),group:user.role==='staff'?'GÜNLÜK OPERASYON':p.group})).sort((a,b)=>user.role==='staff'?(staffOrder.indexOf(a.id)<0?99:staffOrder.indexOf(a.id))-(staffOrder.indexOf(b.id)<0?99:staffOrder.indexOf(b.id)):0);
}
