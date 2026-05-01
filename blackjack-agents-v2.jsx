import { useState, useRef } from "react";

// ─── Deck helpers ───────────────────────────────────────────────────────────
const SUITS = ["♠", "♥", "♦", "♣"];
const VALUES = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];

function newDeck() {
  const deck = [];
  for (const s of SUITS) for (const v of VALUES) deck.push({ suit: s, value: v });
  return deck.sort(() => Math.random() - 0.5);
}

function cardVal(card) {
  if (["J", "Q", "K"].includes(card.value)) return 10;
  if (card.value === "A") return 11;
  return parseInt(card.value);
}

function handScore(hand) {
  let total = hand.reduce((s, c) => s + cardVal(c), 0);
  let aces = hand.filter(c => c.value === "A").length;
  while (total > 21 && aces > 0) { total -= 10; aces--; }
  return total;
}

// Hi-Lo card counting: low cards (2-6) = +1, high cards (10,J,Q,K,A) = -1
function countValue(card) {
  if (["2","3","4","5","6"].includes(card.value)) return 1;
  if (["10","J","Q","K","A"].includes(card.value)) return -1;
  return 0;
}

function cardColor(suit) {
  return suit === "♥" || suit === "♦" ? "#e05b5b" : "#e8e0d4";
}

// ─── Prompt builder ──────────────────────────────────────────────────────────
const BASE_PROMPTS = {
  cautious: `You are a CAUTIOUS blackjack player using basic strategy with risk aversion.
Core rules: Stand on hard 15+. Never hit if you could bust and dealer shows a weak card (2-6). Prefer survival over chasing high scores.`,
  aggressive: `You are an AGGRESSIVE blackjack player who chases strong hands.
Core rules: Always hit until you reach 17+. If the deck is hot (positive count), push even harder. Accept bust risk to maximize wins.`,
};

const FEW_SHOT_EXAMPLES = `
--- FEW-SHOT EXAMPLES (learn from these) ---
Example 1: Hand [10, 6] = 16, Dealer shows 7, Count: 0 → STAND (16 vs dealer 7 is risky but hitting 16 busts often)
Example 2: Hand [5, 4] = 9, Dealer shows 10, Count: -2 → HIT (9 is too low, must hit regardless)
Example 3: Hand [A, 6] = soft 17, Dealer shows 9, Count: +3 → HIT (soft 17 is not strong enough vs dealer 9, deck is hot so take risk)
Example 4: Hand [10, 5] = 15, Dealer shows 4, Count: +1 → STAND (dealer shows weak card 4, likely to bust themselves)
Example 5: Hand [8, 7] = 15, Dealer shows 10, Count: -3 → HIT (dealer 10 is dangerous, deck is cold so take the chance)
---`;

function buildPrompt(strategy, hand, dealerCard, memory) {
  const score = handScore(hand);
  const handStr = hand.map(c => c.value + c.suit).join(", ");
  const recentStr = memory.recentOutcomes.length > 0
    ? memory.recentOutcomes.slice(-5).join(", ")
    : "none yet";
  const countLabel = memory.runningCount > 2 ? "HOT (many low cards gone, high cards coming)" :
    memory.runningCount < -2 ? "COLD (many high cards gone, low cards coming)" : "NEUTRAL";

  return `${BASE_PROMPTS[strategy]}

${FEW_SHOT_EXAMPLES}

--- YOUR MEMORY ---
Hands played: ${memory.handsPlayed}
Recent outcomes (last 5): ${recentStr}
Running card count: ${memory.runningCount} → Deck is ${countLabel}
Win rate so far: ${memory.handsPlayed > 0 ? Math.round((memory.wins / memory.handsPlayed) * 100) : 0}%

--- CURRENT HAND ---
Your hand: ${handStr} (score: ${score})
Dealer's visible card: ${dealerCard.value}${dealerCard.suit}

Using your strategy, your memory, and the few-shot examples above, think step by step.
Consider: your score, dealer's card, the deck count, and your recent performance.
End with exactly one line: ACTION: HIT or ACTION: STAND`;
}

// ─── API call ────────────────────────────────────────────────────────────────
async function callAgent(strategy, hand, dealerCard, memory) {
  const prompt = buildPrompt(strategy, hand, dealerCard, memory);
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      messages: [{ role: "user", content: prompt }],
    }),
  });
  const data = await res.json();
  const text = data.content?.[0]?.text || "";
  const match = text.match(/ACTION:\s*(HIT|STAND)/i);
  const action = match ? match[1].toUpperCase() : "STAND";
  const reasoning = text.replace(/ACTION:\s*(HIT|STAND)/i, "").trim();
  return { action, reasoning };
}

// ─── Card component ──────────────────────────────────────────────────────────
function Card({ card, hidden }) {
  if (hidden) return (
    <div style={{
      width: 48, height: 70, borderRadius: 7, background: "linear-gradient(135deg, #1a3a5c, #0d2137)",
      border: "1px solid #2a5a8c", display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 20, color: "#2a5a8c", flexShrink: 0
    }}>✦</div>
  );
  return (
    <div style={{
      width: 48, height: 70, borderRadius: 7, background: "#fff8f0",
      border: "1px solid #c4a882", display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "space-between", padding: "3px 5px",
      color: cardColor(card.suit), fontFamily: "'Georgia', serif", flexShrink: 0,
      boxShadow: "2px 2px 5px rgba(0,0,0,0.3)"
    }}>
      <span style={{ fontSize: 11, fontWeight: "bold", alignSelf: "flex-start" }}>{card.value}</span>
      <span style={{ fontSize: 20 }}>{card.suit}</span>
      <span style={{ fontSize: 11, fontWeight: "bold", alignSelf: "flex-end", transform: "rotate(180deg)" }}>{card.value}</span>
    </div>
  );
}

// ─── Memory panel ─────────────────────────────────────────────────────────────
function MemoryPanel({ memory, color, activeTab, onTabChange }) {
  const countLabel = memory.runningCount > 2 ? "HOT 🔥" : memory.runningCount < -2 ? "COLD ❄️" : "NEUTRAL";
  const winRate = memory.handsPlayed > 0 ? Math.round((memory.wins / memory.handsPlayed) * 100) : 0;

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
        {["stats", "history", "prompt"].map(tab => (
          <button key={tab} onClick={() => onTabChange(tab)} style={{
            fontSize: 9, padding: "3px 8px", borderRadius: 4, border: "none", cursor: "pointer",
            background: activeTab === tab ? color + "33" : "transparent",
            color: activeTab === tab ? color : "#4a6a7a",
            fontFamily: "monospace", letterSpacing: 1, textTransform: "uppercase"
          }}>{tab}</button>
        ))}
      </div>

      <div style={{
        background: "#06101a", borderRadius: 6, padding: 10, fontSize: 11,
        fontFamily: "monospace", color: "#6a8a9a", lineHeight: 1.7, minHeight: 70
      }}>
        {activeTab === "stats" && (
          <div>
            <div>Hands played: <span style={{ color: "#e8e0d4" }}>{memory.handsPlayed}</span></div>
            <div>Win rate: <span style={{ color }}>{winRate}%</span></div>
            <div>Card count: <span style={{ color }}>{memory.runningCount > 0 ? "+" : ""}{memory.runningCount}</span> → {countLabel}</div>
            <div>Streak: <span style={{ color: "#e8e0d4" }}>{memory.recentOutcomes.slice(-3).join(" → ") || "—"}</span></div>
          </div>
        )}
        {activeTab === "history" && (
          <div>
            {memory.recentOutcomes.length === 0
              ? <span style={{ color: "#2a4a5c" }}>no history yet</span>
              : memory.recentOutcomes.slice(-8).reverse().map((o, i) => (
                <div key={i} style={{
                  color: o === "WIN" ? "#4ae04a" : o === "BUST" || o === "LOSE" ? "#e04a4a" : "#e0c44a"
                }}>{i === 0 ? "► " : "  "}{o}</div>
              ))}
          </div>
        )}
        {activeTab === "prompt" && (
          <div style={{ fontSize: 10, color: "#4a6a7a", whiteSpace: "pre-wrap", maxHeight: 80, overflowY: "auto" }}>
            {BASE_PROMPTS[memory.strategy] || ""}
            {"\n\n[+ few-shot examples + memory context injected per turn]"}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Agent panel ─────────────────────────────────────────────────────────────
function AgentPanel({ agent, gameState }) {
  const [activeTab, setActiveTab] = useState("stats");
  const { name, strategy, hand, reasoning, action, status, memory, isThinking } = agent;
  const color = strategy === "cautious" ? "#4a9e7a" : "#c4623a";
  const label = strategy === "cautious" ? "CAUTIOUS" : "AGGRESSIVE";
  const winRate = memory.handsPlayed > 0 ? Math.round((memory.wins / memory.handsPlayed) * 100) : 0;

  return (
    <div style={{
      flex: 1, background: "#0d1f35", borderRadius: 12, padding: 16,
      border: `1px solid ${color}44`, display: "flex", flexDirection: "column", gap: 10,
      minWidth: 0
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 9, color, letterSpacing: 3, fontFamily: "monospace" }}>{label}</div>
          <div style={{ fontFamily: "'Georgia', serif", fontSize: 17, color: "#e8e0d4" }}>Agent {name}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 9, color: "#6a8a9a", fontFamily: "monospace" }}>WIN RATE</div>
          <div style={{ fontSize: 20, color, fontFamily: "monospace", fontWeight: "bold" }}>{winRate}%</div>
          <div style={{ fontSize: 9, color: "#4a6a7a", fontFamily: "monospace" }}>{memory.wins}/{memory.handsPlayed}</div>
        </div>
      </div>

      {/* Cards */}
      <div style={{ display: "flex", gap: 5, minHeight: 72, alignItems: "center", flexWrap: "wrap" }}>
        {hand.map((c, i) => <Card key={i} card={c} />)}
        {hand.length > 0 && (
          <div style={{
            marginLeft: 6, fontFamily: "monospace", fontSize: 18, fontWeight: "bold",
            color: handScore(hand) > 21 ? "#e05b5b" : "#e8e0d4"
          }}>
            {handScore(hand) > 21 ? "BUST" : handScore(hand)}
          </div>
        )}
      </div>

      {/* Reasoning */}
      <div style={{
        background: "#06131f", borderRadius: 6, padding: 10, minHeight: 72,
        border: `1px solid #1a3a5c`, fontSize: 11, color: "#8ab0c8",
        fontFamily: "monospace", lineHeight: 1.6, overflowY: "auto", maxHeight: 100
      }}>
        {isThinking
          ? <span style={{ color }}>reasoning<span style={{ animation: "blink 1s infinite" }}>...</span></span>
          : reasoning
            ? reasoning
            : <span style={{ color: "#2a4a5c" }}>awaiting turn...</span>}
      </div>

      {/* Action badge */}
      {action && (
        <div style={{
          textAlign: "center", padding: "5px 0", borderRadius: 5,
          background: action === "HIT" ? "#1a3a1a" : "#1a1a3a",
          color: action === "HIT" ? "#4ae04a" : "#4a4ae0",
          fontFamily: "monospace", fontWeight: "bold", fontSize: 13, letterSpacing: 2
        }}>▶ {action}</div>
      )}

      {/* Result badge */}
      {status && (
        <div style={{
          textAlign: "center", padding: "5px 0", borderRadius: 5, fontFamily: "monospace",
          fontWeight: "bold", fontSize: 12, letterSpacing: 1,
          background: status === "WIN" ? "#1a3a1a" : status === "BUST" || status === "LOSE" ? "#3a1a1a" : "#1a2a3a",
          color: status === "WIN" ? "#4ae04a" : status === "BUST" || status === "LOSE" ? "#e04a4a" : "#e0c44a"
        }}>
          {status === "WIN" ? "✓ WIN" : status === "BUST" ? "✗ BUST" : status === "LOSE" ? "✗ LOSE" : "— PUSH"}
        </div>
      )}

      {/* Memory inspector */}
      <MemoryPanel
        memory={{ ...memory, strategy }}
        color={color}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />
    </div>
  );
}

// ─── Main app ────────────────────────────────────────────────────────────────
function initMemory(wins = 0, handsPlayed = 0) {
  return { wins, handsPlayed, runningCount: 0, recentOutcomes: [] };
}

const RESHUFFLE_THRESHOLD = 15; // reshuffle when fewer than 15 cards remain

export default function BlackjackArena() {
  const [gameState, setGameState] = useState("idle");
  const [dealer, setDealer] = useState([]);
  const [agents, setAgents] = useState([
    { name: "Alpha", strategy: "cautious", hand: [], reasoning: "", action: "", status: "", memory: initMemory(), isThinking: false },
    { name: "Beta", strategy: "aggressive", hand: [], reasoning: "", action: "", status: "", memory: initMemory(), isThinking: false },
  ]);
  const [log, setLog] = useState([]);
  const [round, setRound] = useState(0);
  const [deckSize, setDeckSize] = useState(52);
  const [reshuffled, setReshuffled] = useState(false);
  const runningRef = useRef(false);
  // persistent single deck across hands
  const deckRef = useRef(newDeck());
  const deckIndexRef = useRef(0);

  function addLog(msg) { setLog(l => [...l.slice(-40), msg]); }

  async function runGame() {
    if (runningRef.current) return;
    runningRef.current = true;
    setGameState("playing");
    setReshuffled(false);

    // Reshuffle only if deck running low
    const remaining = deckRef.current.length - deckIndexRef.current;
    if (remaining < RESHUFFLE_THRESHOLD) {
      deckRef.current = newDeck();
      deckIndexRef.current = 0;
      setReshuffled(true);
      // reset counts since deck is fresh
      setAgents(prev => prev.map(a => ({ ...a, memory: { ...a.memory, runningCount: 0 } })));
      addLog("⟳ Deck reshuffled — count reset");
    }

    function dealCard() {
      const c = deckRef.current[deckIndexRef.current++];
      setDeckSize(deckRef.current.length - deckIndexRef.current);
      return c;
    }

    const dealerHand = [dealCard(), dealCard()];
    const hands = [[dealCard(), dealCard()], [dealCard(), dealCard()]];

    // compute running count from all cards seen so far
    const allSeen = [...dealerHand.slice(0, 1), ...hands[0], ...hands[1]]; // dealer shows 1 card
    const initialCount = agents.map(a => a.memory.runningCount);

    setDealer(dealerHand);
    setAgents(prev => prev.map((a, i) => ({
      ...a, hand: hands[i], reasoning: "", action: "", status: "", isThinking: false
    })));
    addLog(`── Round ${round + 1} ── Dealer shows ${dealerHand[0].value}${dealerHand[0].suit}`);

    const finalHands = [...hands];

    for (let ai = 0; ai < 2; ai++) {
      let hand = [...hands[ai]];

      // update count: add initial visible cards
      const visibleCards = [...dealerHand.slice(0, 1), ...hand];
      let count = agents[ai].memory.runningCount + visibleCards.reduce((s, c) => s + countValue(c), 0);

      while (true) {
        const score = handScore(hand);
        if (score >= 21) break;

        const memSnapshot = { ...agents[ai].memory, runningCount: count };
        setAgents(prev => prev.map((a, i) => i === ai ? { ...a, isThinking: true, hand, memory: { ...a.memory, runningCount: count } } : a));

        const { action, reasoning } = await callAgent(agents[ai].strategy, hand, dealerHand[0], memSnapshot);
        setAgents(prev => prev.map((a, i) => i === ai ? { ...a, isThinking: false, reasoning, action, hand } : a));
        addLog(`Agent ${agents[ai].name}: ${action} (score ${handScore(hand)}, count ${count > 0 ? "+" : ""}${count})`);

        if (action === "STAND") break;
        const newCard = dealCard();
        count += countValue(newCard);
        hand = [...hand, newCard];
        setAgents(prev => prev.map((a, i) => i === ai ? { ...a, hand, memory: { ...a.memory, runningCount: count } } : a));
        if (handScore(hand) > 21) break;
      }
      finalHands[ai] = hand;
    }

    // Dealer reveals & plays
    // add dealer hole card to count
    const dealerHoleCount = countValue(dealerHand[1]);
    let dHand = [...dealerHand];
    while (handScore(dHand) < 17) dHand.push(dealCard());
    const dealerScore = handScore(dHand);
    setDealer(dHand);
    addLog(`Dealer reveals ${dealerHand[1].value}${dealerHand[1].suit} → final: ${dealerScore > 21 ? "BUST" : dealerScore}`);

    // Determine results + update memory
    setAgents(prev => prev.map((a, i) => {
      const s = handScore(finalHands[i]);
      let status = s > 21 ? "BUST" : dealerScore > 21 || s > dealerScore ? "WIN" : s === dealerScore ? "PUSH" : "LOSE";
      const wins = a.memory.wins + (status === "WIN" ? 1 : 0);
      const handsPlayed = a.memory.handsPlayed + 1;
      // update count: add dealer hole card + dealer hits
      const newCount = a.memory.runningCount + dealerHoleCount +
        dHand.slice(2).reduce((s, c) => s + countValue(c), 0);
      const recentOutcomes = [...a.memory.recentOutcomes, status].slice(-20);
      addLog(`Agent ${a.name}: ${status}`);
      return {
        ...a, status, hand: finalHands[i],
        memory: { wins, handsPlayed, runningCount: newCount, recentOutcomes }
      };
    }));

    setRound(r => r + 1);
    setGameState("done");
    runningRef.current = false;
  }

  function resetScores() {
    deckRef.current = newDeck();
    deckIndexRef.current = 0;
    setDeckSize(52);
    setReshuffled(false);
    setDealer([]);
    setAgents(prev => prev.map(a => ({
      ...a, hand: [], reasoning: "", action: "", status: "", isThinking: false,
      memory: initMemory()
    })));
    setRound(0);
    setLog([]);
    setGameState("idle");
  }

  function nextHand() {
    setDealer([]);
    setReshuffled(false);
    setAgents(prev => prev.map(a => ({ ...a, hand: [], reasoning: "", action: "", status: "", isThinking: false })));
    setGameState("idle");
  }

  return (
    <div style={{
      minHeight: "100vh", background: "#060e18",
      backgroundImage: "radial-gradient(ellipse at 20% 50%, #0a1f0a18 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, #1a0a0a18 0%, transparent 60%)",
      padding: 20, fontFamily: "'Courier New', monospace", color: "#e8e0d4"
    }}>
      <style>{`@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }`}</style>

      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 20 }}>
          <div style={{ fontSize: 9, letterSpacing: 6, color: "#4a7a9a", marginBottom: 4 }}>LLM EVALUATION ARENA · v2</div>
          <h1 style={{ fontFamily: "'Georgia', serif", fontSize: 28, margin: 0, color: "#e8e0d4", fontWeight: "normal" }}>
            ♠ Blackjack Agent Duel ♠
          </h1>
          <div style={{ fontSize: 10, color: "#4a6a7a", marginTop: 4 }}>
            Memory · Few-shot examples · Card counting · Chain-of-thought
          </div>
          <div style={{ display: "flex", justifyContent: "center", gap: 16, marginTop: 6, fontSize: 10, fontFamily: "monospace" }}>
            <span style={{ color: "#4a7a9a" }}>DECK: <span style={{ color: deckSize < 20 ? "#e0c44a" : "#4ae09a" }}>{deckSize}/52 cards remaining</span></span>
            {reshuffled && <span style={{ color: "#e0c44a" }}>⟳ RESHUFFLED THIS HAND</span>}
          </div>
          {round > 0 && <div style={{ fontSize: 11, color: "#6a8a9a", marginTop: 4 }}>Round {round} complete</div>}
        </div>

        {/* Dealer row */}
        <div style={{
          background: "#0a1a2e", borderRadius: 10, padding: 14, marginBottom: 14,
          border: "1px solid #1a3a5c", display: "flex", alignItems: "center", gap: 14
        }}>
          <div style={{ fontSize: 10, color: "#4a7a9a", letterSpacing: 2, width: 56, flexShrink: 0 }}>DEALER</div>
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
            {dealer.length === 0
              ? <div style={{ color: "#2a4a5c", fontSize: 12 }}>no cards yet</div>
              : dealer.map((c, i) => <Card key={i} card={c} hidden={i === 1 && gameState === "playing"} />)}
          </div>
          {dealer.length > 0 && gameState === "done" && (
            <div style={{ marginLeft: 8, fontSize: 16, fontWeight: "bold", color: handScore(dealer) > 21 ? "#e05b5b" : "#e8e0d4" }}>
              {handScore(dealer) > 21 ? "BUST" : handScore(dealer)}
            </div>
          )}
        </div>

        {/* Agent panels */}
        <div style={{ display: "flex", gap: 12, marginBottom: 14 }}>
          {agents.map((a, i) => <AgentPanel key={i} agent={a} gameState={gameState} />)}
        </div>

        {/* Controls */}
        <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
          <button
            onClick={gameState === "playing" ? undefined : gameState === "done" ? nextHand : runGame}
            disabled={gameState === "playing"}
            style={{
              flex: 1, padding: "11px 0", borderRadius: 7, border: "none",
              cursor: gameState === "playing" ? "not-allowed" : "pointer",
              background: gameState === "playing" ? "#1a2a3a" : "linear-gradient(135deg, #1a4a3a, #0d2a1f)",
              color: gameState === "playing" ? "#4a6a7a" : "#4ae09a",
              fontFamily: "monospace", fontSize: 13, fontWeight: "bold", letterSpacing: 2
            }}>
            {gameState === "playing" ? "▶ AGENTS REASONING..." : gameState === "done" ? "▶ NEXT HAND" : "▶ DEAL HAND"}
          </button>
          <button onClick={resetScores} style={{
            padding: "11px 16px", borderRadius: 7, border: "1px solid #2a4a5c",
            background: "transparent", color: "#4a7a9a", cursor: "pointer",
            fontFamily: "monospace", fontSize: 11
          }}>RESET ALL</button>
        </div>

        {/* Legend */}
        <div style={{
          background: "#06101a", borderRadius: 6, padding: 10, marginBottom: 10,
          border: "1px solid #0a2030", fontSize: 10, color: "#4a6a7a", fontFamily: "monospace",
          display: "flex", gap: 20, flexWrap: "wrap"
        }}>
          <span>MEMORY TABS:</span>
          <span><b style={{ color: "#8ab0c8" }}>stats</b> — win rate, card count, streak</span>
          <span><b style={{ color: "#8ab0c8" }}>history</b> — recent outcomes</span>
          <span><b style={{ color: "#8ab0c8" }}>prompt</b> — agent's base strategy</span>
          <span>Count +/- = Hi-Lo card counting (deck hot/cold)</span>
        </div>

        {/* Log */}
        <div style={{ background: "#06101a", borderRadius: 8, padding: 12, border: "1px solid #0a2030", maxHeight: 110, overflowY: "auto" }}>
          <div style={{ fontSize: 9, color: "#2a4a5c", letterSpacing: 2, marginBottom: 6 }}>GAME LOG</div>
          {log.length === 0
            ? <div style={{ color: "#1a3a4a", fontSize: 11 }}>no games played yet</div>
            : [...log].reverse().map((l, i) => (
              <div key={i} style={{ fontSize: 11, color: i === 0 ? "#6a9ab0" : "#2a5a6a", lineHeight: 1.8 }}>› {l}</div>
            ))}
        </div>
      </div>
    </div>
  );
}
