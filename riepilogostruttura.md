# Raccolta e costruzione della Knowledge Base
La knowledge base si forma a partire da:
1. OWASP Cheat Sheets (scenari d'attacco e contromisure): 101 file, ciascuno contenente definizione o gestione di una parte del sistema, problemi tipici e scenari d'attacco con eventuali contromisure suggerite.
2. Definizione precisa dei requisiti funzionali, non funzionali e di sicurezza

Questa base informativa è considerata sufficiente in quanto un LLM, in generale, è addestrato su numerose fonti pubbliche e tecniche, offrendo una varietà di approcci per la risoluzione di qualsiasi tipo di problema. L'aggiunta di contesti e collegamenti alle informazioni riguardanti il sistema desiderato, attraverso scenari di attacco e gestione delle risorse, aumenta la priorità della selezione dei requisiti nella fase generativa.
Dopo la conversione dei documenti OWASP in formato .txt, viene effettuata una fase di labeling e categorizzazione. Ogni documento viene associato a una serie di metadati (es. categoria tecnica, rischio OWASP Top 10, tipo di documento) che ne descrivono il contenuto e la rilevanza. Ad esempio: categoria tecnica trattata (es. autenticazione, gestione sessioni), rischio OWASP Top 10 coinvolto (es. A1 - Broken Access Control), e tipo di documento (guida, raccomandazione, best practice...). Questi metadati sono salvati in formato JSON per facilitarne l’indicizzazione e la tracciabilità. Questa etichettatura supporta il retrieval mirato e la valutazione della completezza rispetto ai temi trattati nei documenti.


# Progettazione dell'architettura RAG
In particolare ci sono 3 fasi che il nostro sistema dovrà seguire:
1. Data Preparation: Si preparano 102 file txt (descritti nella Raccolta e Costruzione della Knowledge base). A causa della dimensione variabile dei seguenti file, si esegue un'operazione chiamata "Chunking", una suddivisione in blocchi delle informazioni grezze.
2. Indicizzazione dei Dati: Subito dopo la preparazione dei dati attraverso il chunking, avremo un insieme di blocchi che serviranno da contesto per le potenziali domande dell'utente da rispondere. Ogni chunk dovrà avere una certa rilevanza (maggiore o minore) in base al tipo di domanda o al tipo di sistema desiderato.
I chunk ottenuti vengono trasformati in vettori semantici tramite un modello di embedding. In questa fase si considerano modelli come all-MiniLM-L6-v2 o text-embedding-3-small (da capire il modello di embeddings finale), scelti per la loro buona combinazione tra performance, leggerezza e qualità semantica. Una volta creati i vettori, quest'ultimi devono essere indicizzati in un database di vettori per abilitare operazioni di ricerca basate su similarità semantica utilizzando la cosine similarity come metrica, poiché confronta l’orientamento dei vettori piuttosto che la loro lunghezza, risultando più adatta per compiti semantici in cui il significato è rappresentato dalla direzione del vettore. Questo consente di catturare similarità concettuali anche in assenza di parole chiave esplicite.
3. Questa fase comprende Information Retrieval ed LLM Inference: In base al sistema desiderato richiesto dall'utente (con prompt engineering per guidare l'LLM), si analizzerà il prompt di input per la restituzione di requisiti generati sulla base dei chunk più rilevanti. Esempio:  Se si specifica che il sistema gestirà credenziali utente, verranno attivati requisiti relativi alla cheat sheet OWASP “Secret Management”.


# Sviluppo di template e prompt engineering
Vi sarà un prompt specializzato, comprendendo informazioni sulle sezioni del RAD che descrivono il sistema target con il suo ambiente circostante.

# Pipeline di generazione e validazione dei requisiti
Il processo iterativo automatico è rappresentato da 4 fasi e va a coprire tutto ciò che inizia con il prompt e termina con l'output:
1. Fase di Contesto Iniziale: Il sistema riceve in input un prompt contenente le sezioni del RAD del sistema desiderato più rilevanti per lo studio dei requisiti. Sulla base di varie analisi si è dedotto che le informazioni su cui basarsi per la determinazione dei requisiti sono maggiori (e meno generiche) durante la stesura del RAD (rispetto ad un semplice Problem Statement, dato da semplici colloqui e generiche richieste prioritarie). 
2. Fase di Retrieve: Viene eseguita un’operazione di retrieval sui chunk più rilevanti tramite il modello RAG, attraverso le best practices di OWASP
3. Fase di Input combinato: si combinano l'input iniziale dell'utente (contesto iniziale) ed il contesto dato dai chunk più rilevanti estratti dagli embeddings
4. Risposta unica generata

Per le metriche di valutazione delle qualità, ci si basa su 4 proprietà:
- Completezza: Tutte le aree di sicurezza sono "sicure"
- Consistenza: Mancanza di contraddizioni
- Tracciabilità: I requisiti derivano dal contesto iniziale + documenti del RAG (cheatsheet OWASP)?
- Sicurezza: sono presenti requisiti OWASP laddove pertinenti

Per l’analisi, è possibile usare:
- LLM specializzati per valutare automaticamente la qualità,
- strumenti strutturati come regole statiche, validatori o checklist, a seconda del tipo di progetto. Si può utilizzare un LLM di supporto come un'analisi statica successiva alla generazione dell'output.

Due possibili strategie di miglioramento:
- Analizzare le priorità di sicurezza per ogni componente del sistema target, rafforzando le aree più critiche.
- Utilizzare un LLM di supporto che verifichi le quattro metriche sopra elencate, individuando aree carenti e suggerendo correzioni.

Grazie alla tracciabilità, indipendentemente dalla strategia d'analisi adottata, è possibile comprendere le aree su cui l'LLM ha generato dei requisiti di sicurezza, funzionali e non, grazie al labeling dei documenti iniziale e al processo iterativo finale dei requisiti, con eventuale validazione ciclata.
La validazione quindi si effettua sulla tracciabilità e la completezza, le proprietà più importanti dato che la prima implica la possibilità di valutare la seconda, mentre la seconda è il focus del progetto.