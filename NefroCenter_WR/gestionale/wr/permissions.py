"""Ruoli e permessi: un'unica tabella usata dal server, dall'interfaccia e dalla demo.

Ogni permesso indica i ruoli che lo possiedono. Alcuni permessi del compilatore
dipendono dai parametri del centro (per esempio la pianificazione): in quel caso
il ruolo è elencato in OPERATOR_FLAGS con il parametro che lo abilita.
L'ambito dei centri è separato: amministratore e HR centrale vedono tutti i centri,
gli altri ruoli solo quelli assegnati.
"""
from dataclasses import dataclass, field

from .errors import Forbidden

ROLES = {
    'admin': dict(label='Amministratore', scope='all', summary='Configura il portale, gli accessi e i servizi del gruppo.'),
    'hr': dict(label='HR centrale', scope='all', summary='Gestisce persone, documenti e processi HR di tutte le strutture.'),
    'manager': dict(label='Responsabile di struttura', scope='assigned', summary='Organizza la struttura assegnata: presenze, persone e verifiche del mese.'),
    'operator': dict(label='Compilatore', scope='assigned', summary='Registra le presenze quotidiane della struttura assegnata.'),
    'viewer': dict(label='Direzione · consultazione', scope='assigned', summary='Consulta andamento, presenze e statistiche senza modificare i dati.'),
}
ROLE_ORDER = ['admin', 'hr', 'manager', 'operator', 'viewer']

ALL = frozenset(ROLE_ORDER)
SITE_WRITERS = frozenset({'admin', 'manager', 'operator'})
SITE_MANAGERS = frozenset({'admin', 'manager'})
HR_AREA = frozenset({'admin', 'hr', 'manager'})
CENTRAL = frozenset({'admin', 'hr'})
ADMIN = frozenset({'admin'})

# permesso -> (ruoli, area, descrizione per guide e riferimento ruoli)
CAPABILITIES = {
    # Presenze
    'presenze.vedi': (ALL, 'Presenze', 'Consultare registro, riepilogo, controlli e storico del mese'),
    'presenze.compila': (SITE_WRITERS, 'Presenze', 'Registrare e correggere presenze nei mesi aperti'),
    'presenze.pianifica': (SITE_MANAGERS, 'Presenze', 'Inserire ed eliminare turni pianificati'),
    'presenze.orari': (SITE_MANAGERS, 'Presenze', 'Modificare orari e pause rispetto alla fascia'),
    'presenze.sede': (SITE_MANAGERS, 'Presenze', 'Indicare una sede di lavoro diversa dalla struttura'),
    'presenze.festivo': (SITE_MANAGERS, 'Presenze', 'Cambiare la classificazione festiva di un turno'),
    'presenze.elimina': (SITE_MANAGERS, 'Presenze', 'Eliminare registrazioni'),
    'presenze.esporta': (frozenset({'admin', 'manager', 'hr'}), 'Presenze', 'Scaricare il registro del mese in CSV'),
    'presenze.anagrafica': (SITE_MANAGERS, 'Presenze', 'Aggiungere o modificare le persone del registro'),
    'presenze.carico': (SITE_MANAGERS, 'Presenze', 'Registrare i pazienti per fascia e consultare il carico'),
    'mese.verifica': (SITE_MANAGERS, 'Presenze', 'Confermare calendario e parametri del mese'),
    'mese.chiudi': (SITE_MANAGERS, 'Presenze', 'Chiudere e riaprire il mese quando l’approvazione non è attiva'),
    'mese.regole': (SITE_MANAGERS, 'Presenze', 'Applicare i parametri più recenti a un mese non ancora compilato'),
    # Approvazione mensile
    'approvazioni.vedi': (ALL, 'Approvazioni', 'Consultare stato e storico dell’approvazione del mese'),
    'approvazioni.invia': (SITE_WRITERS, 'Approvazioni', 'Inviare il mese al responsabile'),
    'approvazioni.verifica': (SITE_MANAGERS, 'Approvazioni', 'Verificare il mese e inoltrarlo a HR, oppure restituirlo'),
    'approvazioni.approva': (CENTRAL, 'Approvazioni', 'Approvare e chiudere il mese verificato'),
    'approvazioni.riapri': (frozenset({'admin', 'hr', 'manager'}), 'Approvazioni', 'Riaprire con motivazione un mese approvato'),
    'approvazioni.configura': (ADMIN, 'Approvazioni', 'Attivare o disattivare il percorso di approvazione di una struttura'),
    # Copertura
    'copertura.vedi': (ALL, 'Copertura', 'Consultare la copertura aggregata dei turni'),
    'copertura.dettagli': (HR_AREA, 'Copertura', 'Vedere nomi, disponibilità e proposte di sostituzione'),
    'copertura.fabbisogni': (SITE_MANAGERS, 'Copertura', 'Definire i fabbisogni minimi'),
    'copertura.disponibilita': (HR_AREA, 'Copertura', 'Registrare disponibilità e indisponibilità'),
    'copertura.proponi': (HR_AREA, 'Copertura', 'Proporre sostituzioni fra strutture'),
    'copertura.decidi': (SITE_MANAGERS, 'Copertura', 'Accettare o rifiutare una sostituzione nella struttura di destinazione'),
    # Persone e HR
    'hr.fascicoli': (HR_AREA, 'Persone', 'Gestire fascicoli, onboarding, scadenze e documenti'),
    'hr.modello': (HR_AREA, 'Persone', 'Configurare attività di onboarding e campi aggiuntivi della struttura'),
    'documenti.verifica': (CENTRAL, 'Persone', 'Verificare i documenti o richiederne la correzione'),
    'documenti.ripresenta': (HR_AREA, 'Persone', 'Ripresentare un documento corretto'),
    'strutture.gestisci': (HR_AREA, 'Persone', 'Consultare e aggiornare la rubrica delle strutture'),
    'gruppo.gestisci': (HR_AREA, 'Persone', 'Collegare identità e registrare decorrenze contrattuali ed economiche'),
    'uscite.gestisci': (HR_AREA, 'Persone', 'Gestire cessazioni, trasferimenti e dotazioni'),
    # Amministrazione del personale
    'accordi.vedi': (HR_AREA, 'Amministrazione', 'Consultare accordi e calcoli del mese'),
    'accordi.modifica': (SITE_MANAGERS, 'Amministrazione', 'Salvare l’accordo individuale del mese'),
    'paghe.gestisci': (HR_AREA, 'Amministrazione', 'Preparare tracciati paghe ed esportazioni per il consulente'),
    'comunicazioni.usa': (CENTRAL, 'Amministrazione', 'Preparare modelli, liste, anteprime e bozze email'),
    'comunicazioni.configura': (ADMIN, 'Amministrazione', 'Configurare il servizio di posta aziendale'),
    'promemoria.vedi': (CENTRAL, 'Amministrazione', 'Consultare configurazione e storico dei promemoria'),
    'promemoria.configura': (ADMIN, 'Amministrazione', 'Configurare e attivare i promemoria automatici'),
    # Analisi
    'statistiche.vedi': (ALL, 'Analisi', 'Consultare statistiche delle strutture autorizzate'),
    'esportazioni.riservate': (HR_AREA, 'Analisi', 'Scaricare prospetti con dati personali (dipendenti, onboarding, accordi)'),
    'gruppo.riepilogo': (frozenset({'admin', 'hr', 'viewer'}), 'Analisi', 'Scaricare il riepilogo mensile di tutte le strutture autorizzate'),
    # Sistema
    'centri.parametri': (SITE_MANAGERS, 'Sistema', 'Modificare fasce, causali, ruoli e regole della struttura'),
    'centri.crea': (ADMIN, 'Sistema', 'Creare, rinominare e disattivare le strutture'),
    'utenti.gestisci': (ADMIN, 'Sistema', 'Creare account, assegnare ruoli e strutture, ripristinare accessi'),
    'backup.gestisci': (ADMIN, 'Sistema', 'Creare, scaricare e copiare i backup'),
    'import.excel': (ADMIN, 'Sistema', 'Importare il modello Excel delle presenze'),
}

# Permessi che il compilatore ottiene solo se abilitati nei parametri del centro.
OPERATOR_FLAGS = {
    'presenze.pianifica': 'operator_planned',
    'presenze.orari': 'operator_edit_times',
    'presenze.sede': 'operator_choose_site',
    'presenze.festivo': 'operator_mark_holiday',
    'presenze.elimina': 'operator_delete',
}
# Esportazione del registro: compilatore e consultazione solo se il centro lo consente.
EXPORT_FLAG = 'operator_export'


@dataclass(frozen=True)
class User:
    id: str
    username: str
    name: str
    role: str
    centers: frozenset = field(default_factory=frozenset)
    active: bool = True

    @property
    def sees_all(self):
        return ROLES[self.role]['scope'] == 'all'

    def public(self):
        return dict(id=self.id, username=self.username, name=self.name, role=self.role,
                    role_label=ROLES[self.role]['label'], centers=sorted(self.centers), active=self.active)


def has(user, capability, config=None):
    """True se l'utente possiede il permesso; config sono i parametri del centro (se rilevanti)."""
    roles = CAPABILITIES[capability][0]
    if user.role in roles:
        return True
    if user.role == 'operator' and capability in OPERATOR_FLAGS and config is not None:
        return bool(config.get(OPERATOR_FLAGS[capability]))
    if capability == 'presenze.esporta' and user.role in ('operator', 'viewer') and config is not None:
        return bool(config.get(EXPORT_FLAG))
    return False


def require(user, capability, config=None, message=None):
    if not has(user, capability, config):
        raise Forbidden(message or f'Operazione non consentita al profilo {ROLES[user.role]["label"]}: '
                        f'{CAPABILITIES[capability][2].lower()}.')


def in_scope(user, center_id):
    return user.sees_all or center_id in user.centers


def require_center(user, center_id):
    if not in_scope(user, center_id):
        raise Forbidden('Struttura non assegnata a questo account.')


def capability_map(user):
    """Permessi generali (senza i parametri di un centro) per l'interfaccia."""
    return {cap: has(user, cap) for cap in CAPABILITIES}


def center_capabilities(user, config):
    """Permessi dipendenti dai parametri di un centro, per la pagina presenze."""
    return {cap: has(user, cap, config) for cap in list(OPERATOR_FLAGS) + ['presenze.esporta']}


def matrix():
    """Tabella completa per la guida dei ruoli: permesso, area, descrizione, ruoli."""
    rows = []
    for cap, (roles, area, text) in CAPABILITIES.items():
        conditional = ['operator'] if cap in OPERATOR_FLAGS else []
        if cap == 'presenze.esporta':
            conditional = ['operator', 'viewer']
        rows.append(dict(id=cap, area=area, description=text, roles=[r for r in ROLE_ORDER if r in roles],
                         conditional=conditional))
    return dict(roles=[dict(id=r, **ROLES[r]) for r in ROLE_ORDER], capabilities=rows)
