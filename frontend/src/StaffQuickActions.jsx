import React,{useState} from 'react';
import {Search,Wallet,IdCard} from 'lucide-react';
import {Button,Field} from './ui';
export function StaffQuickActions({db,navigate}){
  const [query,setQuery]=useState('');const rights=db.personnel?.permissions || {};
  const matches=query.trim()?db.members.filter(m=>`${m.name} ${m.phone||''} ${m.number}`.toLocaleLowerCase('tr').includes(query.toLocaleLowerCase('tr'))).slice(0,5):[];
  return <section className="page-grid"><div className="filter-bar">{rights.memberManagement!==false&&<Field label="Hızlı üye ara"><input type="search" value={query} placeholder="Ad, telefon veya üye no" onChange={e=>setQuery(e.target.value)}/></Field>}{rights.collections!==false&&<Button icon={Wallet} onClick={()=>navigate('payments')}>Ödeme al</Button>}{rights.cardManagement!==false&&<Button icon={IdCard} onClick={()=>navigate('cards')}>RFID kart işlemleri</Button>}</div>{matches.length>0&&<div className="button-group">{matches.map(m=><Button key={m.id} icon={Search} onClick={()=>navigate('members',m.id)}>{m.name} · {m.number}</Button>)}</div>}</section>;
}
