//+------------------------------------------------------------------+
//| TraderDeskCotacoes.mq5                                           |
//| Envia compra/venda (melhor oferta) das calls da lista de rolagem  |
//| para o Trader Desk, a cada poucos segundos.                      |
//+------------------------------------------------------------------+
#property copyright "Trader Desk"
#property version   "1.00"
#property strict

input string InpUrl        = "https://trader-desk.onrender.com/cotacoes/opcoes"; // endereço do receptor
input string InpToken      = "";   // mesmo valor de API_WRITE_TOKEN do servidor (deixe vazio se não usa)
input int    InpIntervalo  = 3;    // segundos entre envios
input string InpSymbols    = "POMOA476,POMOL419,HYPEA267,HYPEL253,VBBRA361,VBBRL319,TENDD268,TENDL195,BEEFD392,BEEFL302,CMINA511,CMINL571,ROXOC115,ROXOD125,ROXOL122,SMALD12,SMALL11";

string g_sym[];
int    g_n = 0;
bool   g_book[];

//+------------------------------------------------------------------+
int OnInit()
  {
   g_n = StringSplit(InpSymbols, ',', g_sym);
   if(g_n <= 0)
     {
      Print("TraderDesk: lista de símbolos vazia.");
      return INIT_PARAMETERS_INCORRECT;
     }
   ArrayResize(g_book, g_n);
   for(int i = 0; i < g_n; i++)
     {
      StringTrimLeft(g_sym[i]);
      StringTrimRight(g_sym[i]);
      bool ok = SymbolSelect(g_sym[i], true);       // coloca no Market Watch
      g_book[i] = ok && MarketBookAdd(g_sym[i]);     // assina o book (profundidade)
      if(!ok)
         PrintFormat("TraderDesk: símbolo %s não encontrado no MT5 (confira o nome).", g_sym[i]);
     }
   EventSetTimer(MathMax(1, InpIntervalo));
   PrintFormat("TraderDesk: monitorando %d símbolos. Lembre de liberar %s em Ferramentas > Opções > Expert Advisors > WebRequest.", g_n, InpUrl);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   for(int i = 0; i < g_n; i++)
      if(g_book[i]) MarketBookRelease(g_sym[i]);
  }

//+------------------------------------------------------------------+
// Melhor compra/venda: usa o book se existir, senão o tick.
bool Cotacao(const string s, double &bid, double &ask, double &bq, double &aq, double &last)
  {
   bid = 0; ask = 0; bq = 0; aq = 0; last = 0;
   MqlTick t;
   if(SymbolInfoTick(s, t))
     {
      bid = t.bid; ask = t.ask; last = t.last;
     }
   MqlBookInfo book[];
   if(MarketBookGet(s, book))
     {
      double bestBid = 0, bestAsk = 0, volBid = 0, volAsk = 0;
      int n = ArraySize(book);
      for(int k = 0; k < n; k++)
        {
         if(book[k].type == BOOK_TYPE_BUY || book[k].type == BOOK_TYPE_BUY_MARKET)
           {
            if(book[k].price > bestBid) { bestBid = book[k].price; volBid = (double)book[k].volume; }
           }
         else if(book[k].type == BOOK_TYPE_SELL || book[k].type == BOOK_TYPE_SELL_MARKET)
           {
            if(bestAsk == 0 || book[k].price < bestAsk) { bestAsk = book[k].price; volAsk = (double)book[k].volume; }
           }
        }
      if(bestBid > 0) { bid = bestBid; bq = volBid; }
      else bid = 0;          // sem comprador no book
      if(bestAsk > 0) { ask = bestAsk; aq = volAsk; }
      else ask = 0;          // sem vendedor no book
     }
   return true;
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   string json = "{\"quotes\":[";
   int enviados = 0;
   for(int i = 0; i < g_n; i++)
     {
      double bid, ask, bq, aq, last;
      Cotacao(g_sym[i], bid, ask, bq, aq, last);
      if(enviados > 0) json += ",";
      json += StringFormat("{\"s\":\"%s\",\"bid\":%s,\"ask\":%s,\"bq\":%s,\"aq\":%s,\"last\":%s}",
                           g_sym[i],
                           DoubleToString(bid, 4), DoubleToString(ask, 4),
                           DoubleToString(bq, 0), DoubleToString(aq, 0),
                           DoubleToString(last, 4));
      enviados++;
     }
   json += "]}";

   char post[], result[];
   int len = StringToCharArray(json, post, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) ArrayResize(post, len - 1);   // tira o terminador nulo
   string headers = "Content-Type: application/json\r\n";
   if(StringLen(InpToken) > 0) headers += "Authorization: Bearer " + InpToken + "\r\n";
   string resHeaders;
   ResetLastError();
   int code = WebRequest("POST", InpUrl, headers, 8000, post, result, resHeaders);
   if(code == -1)
      PrintFormat("TraderDesk: WebRequest falhou (erro %d). Libere o endereço em Ferramentas > Opções > Expert Advisors.", GetLastError());
   else if(code != 200)
      PrintFormat("TraderDesk: servidor respondeu %d: %s", code, CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8));
  }
//+------------------------------------------------------------------+
