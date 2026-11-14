import {CalendarDays, ChartNoAxesColumnIncreasing, House, Moon, UserRound} from "lucide-react";
import type {ReactNode} from "react";

export type MainTab = "dashboard" | "records" | "plan" | "account";
const tabs = [
  {id:"dashboard", label:"홈", Icon:House},
  {id:"records", label:"기록", Icon:ChartNoAxesColumnIncreasing},
  {id:"plan", label:"계획", Icon:CalendarDays},
  {id:"account", label:"마이", Icon:UserRound},
] as const;

export function MainNavigation({active, onNavigate}: {active:MainTab; onNavigate:(tab:MainTab)=>void}) {
  return <nav className="main-tabs" aria-label="주요 메뉴">
    {tabs.map(({id, label, Icon}) => <button key={id} type="button" aria-current={active===id?"page":undefined} onClick={()=>onNavigate(id)}>
      <Icon size={23} aria-hidden="true"/><span>{label}</span>
    </button>)}
  </nav>;
}

export function PageHero({title, description, illustrated, children}: {title:string; description?:string; illustrated?:boolean; children?:ReactNode}) {
  return <header className={`mobile-hero${illustrated?" illustrated":""}`}>
    {illustrated && <span className="hero-brand"><Moon size={23} fill="currentColor" aria-hidden="true"/> 달잠</span>}
    <div className="hero-heading"><div><h1 tabIndex={-1}>{title}</h1>{description&&<p>{description}</p>}</div>{children}</div>
  </header>;
}
