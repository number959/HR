/* Only the visual preference is stored locally. No employee or session data. */
const interfaceStyles={classic:'Attuale',workspace:'Spazio di lavoro',essential:'Essenziale',editorial:'Editoriale'};
let interfaceStyle='classic';
try{const value=localStorage.getItem('presenze-interface-style');if(Object.hasOwn(interfaceStyles,value))interfaceStyle=value}catch{}
function applyInterfaceStyle(value){
 if(!Object.hasOwn(interfaceStyles,value))return;
 interfaceStyle=value;document.body.dataset.interface=value;
 try{localStorage.setItem('presenze-interface-style',value)}catch{}
}
function interfaceStyleControl(){return `<label class="interface-style">Stile<select id="interfaceStyle" aria-label="Stile interfaccia">${Object.entries(interfaceStyles).map(([v,label])=>`<option value="${v}" ${v===interfaceStyle?'selected':''}>${label}</option>`).join('')}</select></label>`}
applyInterfaceStyle(interfaceStyle);
