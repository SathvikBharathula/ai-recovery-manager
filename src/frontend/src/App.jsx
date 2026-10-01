import React, { useState } from 'react';
import { ShieldCheck, Lock } from 'lucide-react';

const MOCK_SCENARIOS = [
  { charge_id: "CHG-1001", shipment_id: "SHP-8801", reason: "Packaging Defect - Missing Polybag", amount: 45.0, assessment: "CONTRADICTED", claim_amount: 45.0, explanation: "Prep record explicitly confirms polybag_present = PASS." },
  { charge_id: "CHG-1002", shipment_id: "SHP-8802", reason: "Warehouse Damaged Unit", amount: 120.0, assessment: "SUPPORTED", claim_amount: 0.0, explanation: "Receiving record confirms unit arrived damaged." },
  { charge_id: "CHG-1003", shipment_id: "SHP-8803", reason: "Unlabeled Unit Penalty", amount: 30.0, assessment: "SILENT", claim_amount: 0.0, explanation: "Zero operational records found for this shipment ID. Claim suppressed." },
  { charge_id: "CHG-1004", shipment_id: "SHP-8804", reason: "Dimension Mismatch Fee", amount: 85.0, assessment: "UNCERTAIN", claim_amount: 0.0, explanation: "Conflicting log data across Receiving and Pack managers." }
];

export default function App() {
  const [filter, setFilter] = useState('ALL');
  const filtered = MOCK_SCENARIOS.filter(c => filter === 'ALL' || c.assessment === filter);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      <nav className="border-b border-slate-800 bg-slate-900/80 px-8 py-4 flex justify-between items-center sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-7 h-7 text-cyan-400" />
          <span className="text-lg font-bold tracking-wider bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">
            AI RECOVERY MANAGER
          </span>
        </div>
        <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-full border border-slate-700 text-xs text-cyan-300">
          <Lock className="w-3.5 h-3.5" /> Tenant: org_demo_alpha
        </div>
      </nav>

      <div className="p-8 max-w-7xl mx-auto space-y-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
            <span className="text-slate-400 text-xs font-semibold">RECOVERABLE CLAIMS</span>
            <p className="text-3xl font-extrabold text-cyan-400 mt-2">$45.00</p>
          </div>
          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
            <span className="text-slate-400 text-xs font-semibold">CLAIM PRECISION</span>
            <p className="text-3xl font-extrabold text-emerald-400 mt-2">100.0%</p>
          </div>
          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
            <span className="text-slate-400 text-xs font-semibold">SILENT CHARGES</span>
            <p className="text-3xl font-extrabold text-slate-400 mt-2">1</p>
          </div>
          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
            <span className="text-slate-400 text-xs font-semibold">UNCERTAIN / REVIEW</span>
            <p className="text-3xl font-extrabold text-amber-400 mt-2">1</p>
          </div>
        </div>

        <div className="flex gap-2 border-b border-slate-800 pb-4">
          {['ALL', 'CONTRADICTED', 'SUPPORTED', 'SILENT', 'UNCERTAIN'].map(status => (
            <button
              key={status}
              onClick={() => setFilter(status)}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                filter === status ? 'bg-cyan-950 text-cyan-400 border border-cyan-500/40' : 'text-slate-400 hover:bg-slate-900'
              }`}
            >
              {status}
            </button>
          ))}
        </div>

        <div className="space-y-4">
          {filtered.map(charge => (
            <div key={charge.charge_id} className="p-6 rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-cyan-300 font-bold">{charge.charge_id}</span>
                  <span className="text-xs text-slate-500">• {charge.shipment_id}</span>
                </div>
                <p className="text-sm font-medium text-slate-200">{charge.reason}</p>
                <p className="text-xs text-slate-400">{charge.explanation}</p>
              </div>
              <div className="flex items-center gap-6">
                <div className="text-right">
                  <span className="text-xs text-slate-500 block">Fee Amount</span>
                  <span className="font-bold text-slate-200">${charge.amount.toFixed(2)}</span>
                </div>
                <div className={`px-3 py-1.5 rounded-lg text-xs font-bold border ${
                  charge.assessment === 'CONTRADICTED' ? 'bg-emerald-950/80 text-emerald-400 border-emerald-500/30' :
                  charge.assessment === 'SUPPORTED' ? 'bg-slate-800 text-slate-400 border-slate-700' :
                  charge.assessment === 'SILENT' ? 'bg-slate-900 text-slate-500 border-slate-800' :
                  'bg-amber-950/80 text-amber-400 border-amber-500/30'
                }`}>
                  {charge.assessment}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}