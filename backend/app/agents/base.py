import re

from app.memory.store import load_agent_memory, retrieve_relevant_memories
from app.models.game import (
    COMMON_WOLF_ROLES,
    GOD_ROLES,
    GameState,
    Player,
    ROLE_DESCRIPTIONS,
    ROLE_NAMES_ZH,
    Role,
    VISIBLE_PACK_WOLF_ROLES,
    WOLF_ROLES,
    WitchSelfSaveRule,
    WinRule,
    summarize_rules,
)


def build_rules_summary(game: GameState) -> str:
    win_text = {
        WinRule.SLAUGHTER_SIDE: "本局采用屠边：狼人杀光所有神职或所有平民中的任意一边即可获胜。",
        WinRule.TOTAL_ELIMINATION: "本局采用屠城：狼人必须杀光全部好人才能获胜。",
        WinRule.PARITY: "本局采用人数相等判胜：狼人数量大于等于好人数量时狼人获胜。",
    }[game.rules.win_rule]
    self_save_text = {
        WitchSelfSaveRule.NEVER: "女巫本局不可自救。",
        WitchSelfSaveRule.FIRST_NIGHT_ONLY: "女巫本局仅首夜可自救。",
        WitchSelfSaveRule.ALWAYS: "女巫本局任意夜晚都可自救。",
    }[game.rules.witch_self_save_rule]
    guard_save_text = "同守同救的目标本局会死亡。" if not game.rules.same_guard_save_survives else "同守同救的目标本局会存活。"
    white_wolf_text = "白狼王本局可在白天发言阶段自爆带人。" if game.rules.white_wolf_explode_during_day else "白狼王仅在被放逐后触发带人。"
    sheriff_text = (
        f"本局有警长与警徽机制：首个白天先竞选警长，警长投票权重为 {game.rules.sheriff_vote_multiplier:g}。"
        "发言顺序：警长存活时从警长下一位顺时针发言，警长最后一个发言，之后警长归票（公开投票），其余人同时投票（知道警长的票）；警长不存在时从最近死亡者下一位开始发言。"
        "平票时由警长归票。"
        "若是首夜后进入警长竞选，竞选期间昨夜死讯尚未公布；不要把「未公布死讯」理解成「平安夜」。"
        if game.rules.sheriff_enabled
        else "本局没有警长与警徽机制。发言从最近死亡者下一位开始，无归票环节，所有人同时投票。"
    )
    return "\n".join([win_text, self_save_text, guard_save_text, white_wolf_text, sheriff_text])


WEREWOLF_RULES = """## 狼人杀基础规则

### 夜晚行动顺序
狼人 -> 狼美人 -> 女巫 -> 预言家 -> 守卫 -> 石像鬼 -> 禁言长老 -> 守墓人

### 白天流程
若启用警长：首夜结束后先警长竞选，竞选期间不公布昨夜死讯；警长竞选结束后才公布死亡、首夜遗言、依次发言、可能发生骑士决斗或高风险狼人自爆、警长归票、投票放逐
若未启用警长：首夜天亮后直接公布死亡、首夜遗言、依次发言、可能发生骑士决斗或高风险狼人自爆、投票放逐
发言顺序：
- 若警长存活：从警长下一位开始顺时针发言，警长最后一个发言。发言结束后警长归票（公开自己的投票建议），然后所有人同时投票（归票阶段大家已经知道警长的投票）。
- 若警长不存在或已死亡：从最近死亡者下一位开始发言，无归票环节，所有人同时投票。
除首夜死亡外，第二夜及之后的夜间死亡没有遗言；白天被投票放逐的人仍有遗言。

### 常见技能提醒
- 猎人、狼王因非中毒原因死亡时可以开枪带人（包括被投票放逐、夜晚被刀、被决斗等；中毒和自爆不能开枪）
- 猎人或狼王开枪只知道公开信息和自己的身份；不能因为可开枪就知道谁是真狼，除非该信息已经由公开发言、公开投票、公开死亡或你的合法秘密信息推出
- 普通狼人、狼美人、隐狼、恶灵骑士、石像鬼在规则层面允许白天自爆；白狼王自爆时还能额外带走一人
- 但狼人自爆是高代价战术，不是常规操作。自己身份大概率暴露、自己即将被放逐、需要立刻截断白天关键信息，或白狼王等特殊狼牌能产生明确技能收益，通常都是高收益信号；队友被怀疑本身往往不是充分理由
- **狼王特别注意**：虽然规则也允许白天自爆，但狼王的枪只在被放逐或非中毒死亡时触发——自爆不能开枪。狼王被归票时应坦然接受放逐，出局后开枪带走关键神；自爆等于白送一条命。只有在你确认自己今晚必吃毒（中毒死亡不能开枪）且无法被守卫保护时，自爆才可能优于被毒
- 白痴被投票放逐时翻牌免死，之后失去投票权
- 禁言只影响发言，不影响投票
- 守墓人每晚得知前一天被放逐者是否是狼人阵营

### 死亡与身份公开规则（重要）
- **普通死亡不公开身份**：夜晚被刀、白天被投票放逐的玩家，死亡后**不会**自动公开真实身份。你只能从遗言、生前的公开发言和投票来推断死者的身份，不能假定「投出去就知道身份」。
- **哪些情况会公开身份**：①狼人自爆（立刻公开狼人身份并进入夜晚）②白狼王自爆带人（公开白狼王身份）③白痴被放逐翻牌（公开白痴身份，免死但失去投票权）④骑士决斗成功/失败（双方身份公开）。
- **对狼人的影响**：被放逐的好人不会翻牌，所以好人阵营也无法通过放逐结果直接验证身份。同样，被放逐的狼人（除自爆外）也不会翻牌。这意味着你可以声称被放逐的某人是「狼人/好人」而不会被立刻揭穿——但真预言家、守墓人等可能有查验/感知能力。
- **对好人的影响**：除非自爆或白痴翻牌，否则放逐结果的真实身份对所有人都是隐藏的。不要假定别人知道放逐者的身份。发言中引用死者身份时，要基于遗言、生前发言和投票，而非「大家现在都知道他是X了」。
"""


WOLF_STRATEGY_REFERENCE = """## 狼队公共策略资料
以下是从常见狼人杀攻略抽象出的战术工具箱，只提供可选思路，不是系统命令；请按当前座位、发言顺序、票型、队友状态和公开证据自行取舍。

### 一、狼队分工体系（避免全员抢同一件衣服）
狼队不需要人人做同样的事。请在 private_note 的"狼队计划："里明确自己的公开定位，并与队友形成配合：
- **悍跳狼（台面核心）**：上警抢警徽，报假验人，给警徽流，目标是抗推真预言家。单人悍跳是常规打法；双悍跳（两狼同时跳预言家）虽然操作难度高，但能制造「真假预言家不止一个」的复杂局面，让好人更难判断。
- **冲锋狼（明面站边）**：公开猛站悍跳狼的边，找真预言家发言和逻辑漏洞，帮悍跳狼拉票。投票时与悍跳狼同向。
- **倒钩狼（潜伏对方阵营）**：站边真预言家，混入好人阵营，关键时刻反水冲票。如果全队都倒钩，悍跳狼在台上就没有了公开支持者；如果全队都冲锋，真预言家身边就没有了"信服者"。两种极端格局各有风险和收益——没有哪个是绝对错误的。
- **深水狼（隐藏到底）**：全程低调划水，不站明确边，晚期穿神职衣服或利用信息差制造抗推位。
- **补位原则**：上警前先判断是否已有确认队友准备悍跳。如果有队友悍跳，你可以冲锋配合、可以倒钩潜伏、也可以双悍跳打多重压力。全队冲锋可以碾压式抢警徽，全队倒钩可以藏住狼队结构等残局反水——关键不是选什么，而是**你选这个方案的理由是什么、它打算怎么赢**。想清楚，然后执行。

### 二、悍跳预言家实战指南
悍跳预言家不是只喊"我是预言家"。你需要准备一套完整、自洽的假信息体系：
- **首夜验人结果**：必须明确说出「我昨晚验了X号，他是金水/查杀」。不能只说「我有验人」而不报具体对象和结果。
- **验人理由**：解释为什么验这个位置——「验警下X号是想拉票确认身份」、「验后置位X号是因为他在我旁边我想定义边界」、「验X号是因为他上局表现强势我需要确认」。理由不需要完美，但必须有，否则好人会追问。
- **金水策略**：发金水给警下玩家可以拉票（真实感强，操作难度低）；发金水给狼队友可以做身份（需队友配合支撑，被识破会殃及队友）；不建议给已上警的人发金水（无法拉票且容易被反逻辑）。
- **查杀策略**：发查杀给前置位可以施压博心态；发查杀给划水民可以制造扛推位；狼踩狼（查杀狼队友）是高风险高回报战术——队友自爆可坐实你的"预言家"身份，但配合失误会双狼出局。绝对不要查杀昨晚被刀死的人（直接聊爆）。
- **警徽流**：必须给出后续验人顺序（至少2个），覆盖至少1个警下摇摆位+1个焦点位。例如："警徽流先验X号再验Y号，X号是警下还没表态的，Y号是刚才发言有争议的。"

### 三、银水利用战术（穿女巫衣服必读）
银水指被女巫救起的人，自带隐形身份加持。穿女巫衣服时必须处理银水信息：
- **报真银水（最稳）**：如果你知道真实的夜晚救人信息，直接报真银水。真实信息最容易自洽，不容易被真女巫拍死。
- **报假银水（高风险）**：声称某人是你的银水，但实际不是。如果报给狼队友做身份，需要队友配合；如果报给好人，一旦真女巫起跳对跳银水信息，你会直接暴露。只在真女巫已死或大概率不会起跳时考虑。
- **被查杀时跳女巫报银水（极限操作）**：当你被查杀时起跳女巫，把银水报给悍跳狼可以拉低其预面。但此操作风险极高：真女巫一旦起跳你直接出局。更稳的做法是报一个真实存活好人的银水。
- **自刀骗药（高端局慎用）**：预判女巫首夜会救人，自刀骗解药坐实"银水好人"身份。新手狼队不建议首夜自刀，因为女巫可能不救导致直接减员。
- **核心原则**：穿女巫衣服前，先核对公开夜晚死亡信息。如果你声称是女巫但银水和毒人逻辑与公开死亡矛盾，会立刻暴露。

### 四、警上阶段决策框架
- 上警前明确：我是否悍跳？如果跳，准备验人+警徽流+应对真预言家的话术；如果不跳，选择冲锋/倒钩/深水并写进 private_note。
- 如果已经有确认队友起跳预言家：优先配合而非重复起跳。多人同时悍跳只会让好人说"狼队乱了"。
- 如果狼队无人悍跳：真预言家的验人和警徽流会持续扩张信息优势。此时要么你自己跳，要么用其他神职衣服+票型打法补足压力。
- 不要"等队友悍跳"而不做任何准备。如果最终没人跳，整个狼队在警上阶段已经输了一半。

### 五、常见失误避坑
- **聊爆狼视角**：不能说「我知道X号是好人」、「我觉得Y号像神职」——这些是狼人视角信息。所有发言必须基于「预言家验人」或「闭眼好人推理」视角。
- **多人悍跳相互拆台**：当两个狼队友都跳预言家但验人信息互相矛盾时，好人会判定"至少一狼在悍跳"。此时应有一方主动退水或改口，统一口径。
- **警徽流随意**：只验警上不验警下、只验焦点不验摇摆位、或完全不给警徽流，都会被好人抓住打。
- **发言模糊**：避免「可能」「应该」「大概」等模糊词。悍跳预言家时发言要果断，要有「我就是预言家」的气势。
- **被攻击时崩盘**：当有人质疑你时，用你准备的验人逻辑和警徽流回应，而不是紧张改口或沉默。预设被质疑的回应话术。

### 六、进阶打法：垫飞与阴阳倒钩
- **垫飞（阴阳倒钩）**：站边真预言家，但发言故意做得差、逻辑刻意漏洞百出、或者猛打真预言家的"狼队友"（实际是好人）。目的是让好人怀疑"这个站边真预言家的人发言这么差，真预言家团队质量低"，从而反向拉低真预言家的可信度。与普通倒钩的区别：倒钩是做高自己身份潜伏，垫飞是做差自己身份来污真预言家。
- **垫飞操作要点**：发言要"差但不像演的"——刻意程度太高会被识破。常见垫飞手段：故意忽略关键信息、故意保一个明显像狼的玩家、故意打一个公认好人、投票与发言矛盾。
- **垫飞风险**：如果好人识破你是垫飞，真预言家反而被坐实；如果队友没意识到你在垫飞，可能误以为你是真倒钩。

### 七、狼刀策略进阶
- **混乱视角刀**：优先刀明好人（而不是刀神）。场上明好人越少，所有人的身份越混乱，狼人就越容易靠发言扛推好人。此策略适合发言能力强的狼队。
- **警徽流刀**：如果真预言家留了警徽流（比如"先验A后验B"），刀掉预言家后警徽传给A→好人知道A是金水；此时考虑刀A破坏信息链。但要计算轮次是否划算。
- **追刀**：如果第一夜刀中神（比如女巫救人暴露了银水身份），第二夜继续追刀该目标，不给喘息机会。
- **空刀**：高端局极端操作，故意一夜不刀人，制造平安夜假象扰乱好人判断。风险极高，一般不推荐。
- **自刀时机**：首夜自刀骗药适用于女巫大概率救人的局；中后期自刀通常不值得，因为轮次宝贵。只有悍跳狼或需要坐实银水身份时才考虑自刀。
- **屠边刀法**：明确本局是屠神边还是屠民边。屠神：优先刀已暴露或疑似神职；屠民：避开明神，专刀身份不做的位置。通过发言和投票信息抿身份，不要乱刀。

### 八、残局收割策略
- 当场上存活人数较少（≤5人）时，每一票都致命。此时狼队的核心任务不是再隐藏身份，而是计算票数能否绑票。
- **绑票判断**：如果剩余狼人数 ≥ 剩余好人数的一半，考虑直接冲票绑票获胜，不再隐藏。
- **残局身份利用**：穿一件无法被证伪的衣服（如守卫、白痴），制造"我是神，你不能出我"的局面。
- **深水狼残局收割**：前期全程倒钩/深水的狼人，残局时好人互打、坑位紧张，深水狼的高身份价值最大化。
- **关键刀口**：残局的夜晚刀人决定胜负。刀错一个人可能直接输。优先刀能验证身份的玩家、或身份明确带队的好人。
"""

WEREWOLF_GLOSSARY = """## 狼人杀术语词典
以下是狼人杀常用术语的精确含义。请确保你在使用这些术语时，理解其具体含义，并在发言中给出具体信息，而不仅仅是喊术语名称。

### 验人与身份信息
- **金水**：预言家验出来的好人。说「X号是我的金水」意味着你（作为预言家）昨晚查验了X号，结果是好人身份。必须同时说明：验的是谁、第几夜验的、为什么验他。
- **查杀**：预言家验出来的狼人。说「X号是我的查杀」意味着你查验了X号，结果是狼人。必须同时说明验人理由和查验时间。
- **银水**：被女巫用解药救起的人。说「X号是我的银水」意味着你是女巫，在第Y夜用解药救了X号。必须具体到哪一夜、救了谁。只喊「银水」而不说是谁的银水、哪一夜救的，等于没说。
- **铜水**：被守卫守中而免于死亡的人（通常与女巫救药重合导致同守同救）。守卫报守人信息时必须具体到守了谁、哪一夜守的。
- **警徽流**：预言家安排的后续验人顺序。说「警徽流先X后Y」意味着：如果我今晚死了，警徽传给X代表X是金水，传给Y代表Y是查杀。警徽流必须给出至少2个具体号码和顺序，以及为什么选这两人的理由。只喊「我留了警徽流」而不说具体验谁，是空话。

### 狼队战术
- **悍跳**：狼人冒充预言家（或其他神职）起跳。悍跳预言家需要完整包装：验人结果+验人理由+警徽流+应对真预言家的话术。
- **倒钩**：狼人站边真预言家，混入好人阵营，关键时刻反水。倒钩不是默认安全路线，需要有明确的反水时机和收益判断。
- **冲锋**：狼人公开站边悍跳狼队友，猛打真预言家。冲锋狼需要找到真预言家的具体逻辑漏洞，而不是空喊「我不信他」。
- **深水**：狼人全程低调，不暴露站边，晚期再穿衣服或制造混乱。深水狼需要准备好晚期起跳的身份和口径。
- **狼踩狼**：两个狼人互相攻击/查杀，制造对立假象。高风险高回报——可以互相做身份，但配合失误会双狼出局。
- **自刀**：狼人晚上刀自己人（通常是悍跳狼自刀骗女巫解药）。目的是骗取银水身份加持。新手慎用，女巫可能不救。

### 投票与轮次
- **归票**：警长或带队者在投票前指定的放逐目标。归票不等于最终投票结果，但警长归票具有很强的导向性。
- **冲票**：狼队集中投票给同一个目标，试图强行放逐某人。冲票需要计算票数是否足够。
- **分票/压票**：狼队分散投票或弃票，避免暴露抱团。安排在1-2人弃票或投不同目标。
- **扛推**：将好人（通常是平民）推上放逐位。说「X号是扛推位」意味着X号发言差/身份不做好的好人，容易被狼人利用放逐。
- **PK**：平票时进入对决发言环节，平票的两人分别做最后一轮发言后重新投票。
- **轮次**：游戏进行的天数。说「抢轮次」意味着某方需要在当前天数内达成目标，否则会输。

### 身份与发言
- **穿衣服**：谎称自己有某个神职身份。穿衣服需要准备该身份的完整信息（验人/守人/救人之类），不能只喊身份。
- **脱衣服/退水**：放弃之前声称的身份。退水需要有合理解释（如「我是民，刚才穿衣服是为了挡刀」），否则会被当成狼。
- **表水**：被怀疑时解释自己的身份和投票逻辑，试图洗清嫌疑。表水需要逻辑自洽，不能前后矛盾。
- **拍身份**：直接亮明自己的真实身份（或声称的身份）。拍身份是最后的防守手段，一旦拍出就不能改口。
- **挡刀**：平民故意跳神职，吸引狼人刀口，保护真神。挡刀成功的平民会被狼人误杀，但保护了真神。
- **抿身份**：通过发言、投票、表情推断别人的真实身份。狼人抿神是为了找刀口，好人抿狼是为了找抗推。

### 常见误区
- 喊术语不等于提供信息。如果你说「我留警徽流」但不说验谁、为什么验、什么顺序，等于没留。
- 如果你说「X是银水」但不说你是女巫、哪一夜救的，这信息没有价值。
- 狼人在公开发言中使用术语时，必须配套具体信息；否则好人一眼就能看出你是「名词党」——只会说术语但说不出实质内容。

### 逻辑类型框架
理解以下三种逻辑类型，用于分析他人发言和构建自己的发言：

- **正逻辑**：从好人视角出发的合理推理。例如："A是预言家，他给B发金水，B发言时对A的质疑是合理的，所以B不太可能是A的狼队友在做身份"。正逻辑的核心是代入好人闭眼视角，逻辑链完整且有概率成立。
- **反逻辑**：从狼人视角出发的推理。例如："如果A是狼，他不会在这种情况下给警下仅有的两张牌发查杀，因为这样拉不到票且容易暴露。所以A选择发查杀反而降低了他是狼的概率"。反逻辑需要评估狼队收益，不能空想。
- **伪逻辑**：看似有道理但实际缺乏合理依据的逻辑。例如："A起跳给警后B金水，如果A是狼，后置位还有狼队友为什么还要起跳？所以A一定是预言家"——这是伪逻辑，因为狼人可以发金水博力度，队友起跳也可以是多重保险。

**发言时请自检**：你使用的逻辑是正逻辑、反逻辑、还是伪逻辑？如果你是狼人在编造发言，尽量使用正逻辑和反逻辑，避免使用伪逻辑（容易被识破）。如果你是好人，在质疑他人时，判定对方的逻辑类型可以帮助你判断他是在找狼（好人思路）还是在找抗推（狼人思路）。

### 视角分析基础
- **睁眼发言**：发言中利用了超出闭眼玩家能知道的信息。例如：默认某人是好人、知道剩余狼人数、在未听发言时给身份定义。
- **视角缺失**：狼人在听同伴发言时注意力低于听好人发言，发言时容易缺失对同伴发言的点评。也可刻意忽略同伴的爆狼细节以保护队友。
- **视角偏差**：两个玩家对外置位身份定义差异很大，但A却给了B好人/狼人身份，A的视角就有问题。
- **逻辑断层**：阐述A时突然中断跳到B，随后再回到A或直接放弃。可能是狼人编造发言时思路断裂，但好人也可能出现（忘了思路/时间限制），需要结合语境判断。
- **心态断层**：玩家的情绪状态与其声称的身份/立场不匹配。例如：被查杀后异常轻松（不像真好人被冤枉的反应）、自称平民但语气像神职一样笃定、被质疑时过度防御或过度冷漠。心态断层比逻辑断层更难伪装，是抿身份的重要维度。

### 爆狼发言与爆水发言
- **爆狼发言**：发言中出现只有狼人才能知道的信息，从而暴露身份。典型爆狼：默认某人是好人、知道剩余狼人数、在无人报死亡时提及死亡方式（如「被毒的」）、提及狼队夜话内容、替未发言的人提前开脱。
- **爆水发言**：发言中出现天然的好人视角信息，让其他人相信你是真好人。典型爆水：对局势的困惑感真实（狼人知道真相所以不会真困惑）、对身份判断的犹豫和修正过程自然、主动提及自己可能出错的地方、不急于给所有人定身份。
- 作为狼人：识别爆水发言 → 此人刀口优先级高（因为好人面大，留着危险）。作为好人：识别爆狼发言 → 此人推优先级高。

### 狼队进阶概念
- **洗团队**：狼队通过自刀、狼踩狼、垫飞等操作，让己方成员的公开身份看起来更做好，提高整体存活率。洗团队需要全队配合，单狼无法完成。
- **双爆**：两个狼人在同一天内自爆。目的是跳过讨论和投票环节，直接进入夜晚，加速游戏节奏。通常在狼队需要抢轮次、保护关键狼队友、或扰乱好人信息链时使用。
- **狼队收益**：评估一个狼队操作是否值得的量化标准。收益=预期效果÷风险成本。例如：悍跳狼自刀骗药——收益=银水身份加持+抗推真预言家；风险=女巫不救→减员。只有当收益明显大于风险时才执行。
- **排水法**：当无法通过逻辑确定狼人时，好人采用的排除法——优先出掉信息最少、发言最空洞的玩家。深水狼需要警惕排水法：如果全场只有你一个人没说任何实质信息，你会在排水法中被优先放逐。应对：即使做深水，也要在发言中制造一些可验证的观点和判断。

### 语境分析与代入视角
- **语境分析**：不只看某句话本身，而是分析这句话在当前轮次、当前局势下是否合理。同一个人在不同局势下说同样的话，可信度可能完全不同。语境分析的三要素：1）当前轮次（第几天，还剩几人）2）此人之前的发言和投票记录是否一致 3）此人发言动机（他为什么此时说这句话？对谁有利？）。
- **代入视角**：假设自己是另一个玩家，从TA的已知信息出发，判断TA的发言和行为是否合理。狼人必须掌握代入视角：代入好人视角来编造合理发言；代入预言家视角来伪造验人逻辑；代入女巫视角来伪造银水和毒人逻辑。代入视角的核心问题是：如果我真的有这个身份，我此时会做什么？会说什么？
- **先入为主**：人类认知偏差，第一个信息会锚定后续判断。在狼人杀中体现为：第一个跳预言家的人天然获得更高的信任度（所以狼队要抢先起跳）；第一个被报出银水的人更容易被默认是好人。利用先入为主：悍跳狼尽量第一个起跳；好人要警惕先入为主，不要因为是第一个起跳就轻信。
- **数据库**：老玩家脑中积累的「类似局势→类似结果」模式库。当看到与历史游戏相似的局面时，会调用过去的判断。AI玩家应将每局的关键决策和结果记录为经验（memory），在后续对局中参考类似局面。

### 不见面关系
- **不见面关系**：两个玩家之间缺乏直接的攻防互动，暗示他们可能属于同一阵营（因为队友之间不需要公开互动也能协调）。狼队利用不见面关系：刻意与狼队友在公开发言中保持距离、不互相点评、不共同投票——制造「我们不像认识的」假象。好人识别不见面关系：如果A和B全程零互动，而两人都在焦点位，可能需要警惕是否存在暗线。
- **对立面制造**：狼队通过狼踩狼、互打、分票等手段制造公开的「对立」，让好人以为两人不是队友。对立面制造成功的关键：矛盾要真实（有具体的逻辑冲突点，而非空洞互骂）、力度要适当（太轻微不像真对立，太激烈可能双双出局）。

### 角色特点介绍
以下是各角色的技能、阵营属性和战略要点。理解每个角色的特点有助于你判断场上身份分布、选择穿哪件衣服、以及识别他人的身份线索。

#### 狼人阵营

- **普通狼人**：夜晚与狼队友共同决定刀口。技能简单但团队协作性强——你的价值在于发言、投票和配合队友战术。可以白天自爆（截断讨论、吞警徽、保队友），但自爆不能带人。
- **狼美人**：每晚可魅惑一名玩家；自己出局时（无论被放逐、被刀、被毒还是自爆），被魅惑者一起殉情。关键特点：魅惑是每夜绑定、死亡时才触发——魅惑对象的选择影响全局。被魅惑的玩家不知道自己被魅惑。狼美人出局殉情可以额外带走一人，因此狼美人被归票时可以坦然接受（拉一个垫背），也可以选择自爆（同样触发殉情）。
- **白狼王**：白天发言阶段可以自爆并带走一名玩家。这不是被动技能——你需要在自爆窗口主动选择目标。自爆带人收益最高，可以直接带走预言家/女巫改变轮次。关键区别：白狼王的技能靠**自爆**触发，与狼王（靠被放逐触发）完全相反。
- **狼王**：被投票放逐或非中毒死亡时可以开枪带人。关键硬边界：①自爆不能开枪 ②中毒死亡不能开枪。核心策略：被归票时接受放逐，出局后开枪带走预言家或女巫。不要自爆——自爆等于放弃你的带人能力。你的技能触发条件与猎人一致，这意味着对跳猎人是你的天然选择。
- **隐狼**：所有普通狼人存活时，你不与其他狼队友互认（你不知道他们，他们也不知道你），且被预言家查验显示为好人。所有普通狼人出局后你觉醒，获得夜刀。关键策略：你是天然的"深水位"——真预言家验你是金水，好人很难怀疑你。存活期以好人身份积累信誉，觉醒后收割残局。
- **恶灵骑士**：被预言家查验时，预言家死亡；被女巫毒时，女巫死亡（反噬）。你有天然的"验人免疫"——真预言家不敢验你，因为验你会死。这意味着你可以大胆悍跳或冲锋而不用担心被验出狼身份。但注意：被放逐、被刀、被决斗照样会死。
- **石像鬼**：普通狼人存活时不参与狼刀，每晚可查验一名玩家的准确身份（直接知道对方是什么角色）。所有普通狼人出局后觉醒获得夜刀。你是狼队的"情报官"——你掌握的信息精度甚至超过预言家。关键：你查到的身份信息应通过发言间接传递给队友（但不能太直白以免暴露）。

#### 神职阵营

- **预言家**：每晚查验一名玩家是好人还是狼人。查验结果是对好人阵营最可靠的公开信息来源（真预言家前提下）。预言家通常会上警抢警徽，通过警徽流传递验人信息。对狼人的影响：真预言家是狼队必须处理的目标——要么悍跳对抗，要么尽早刀掉。预言家死后警徽流向会传递最后的验人结果。
- **女巫**：拥有一瓶解药和一瓶毒药，各只能用一次，每晚最多用一瓶。解药可以救活夜晚被刀的玩家（首夜几乎必救）；毒药可以直接毒死一名玩家。女巫知道每晚谁被刀（但不一定知道刀口是谁干的）。对狼人的影响：女巫的毒药可以越过票型直接减员，是狼队最大的威胁之一；自刀骗药需要预判女巫会救。女巫身份需要隐藏，暴露后大概率被刀。
- **猎人**：被放逐或因非中毒原因死亡时可以开枪带人。猎人是"出局威慑"——没人想放逐猎人，因为猎人出局会带走一人。对狼人的影响：刀猎人也会触发开枪，所以猎人通常不是优先刀口（除非确保能扛推）。穿猎人衣服是狼人的有效威慑手段——自称猎人会让好人不敢票你。
- **守卫**：每晚守护一名玩家免受狼刀，通常不能连续两晚守同一人。守卫是"防守端"的核心神职——与女巫解药配合可以创造平安夜。关键博弈：守预言家还是守女巫？守已知好人还是守自己？对狼人的影响：守卫的存在让刀口不确定——刀预言家可能被守、刀女巫可能被守、刀深水目标也可能被守。狼队在刀人时需要考虑守卫的守护逻辑。
- **白痴**：被投票放逐时翻牌免死，翻牌后永久失去投票权。白痴是"放逐安全阀"——好人在放逐决策中误出白痴不会直接减员。对狼人的影响：白痴身份很难扛推（放逐了不死还坐实身份），需要靠刀解决。平民可以穿白痴衣服躲避放逐。
- **骑士**：白天讨论阶段可以决斗一名玩家，若对方是狼人则其死亡，否则自己死亡。骑士是"一命换一命"的高风险高收益神职——决斗成功直接击杀狼人并坐实骑士身份；决斗失败自己死亡。对狼人的影响：骑士的决斗是狼人最怕的单点爆发——瞬间减员且无法防御。悍跳狼在被决斗威胁下需要格外小心。
- **守墓人**：每晚得知前一天被放逐者是否属于狼人阵营。守墓人是"结果验证者"——能确认放逐结果是否正确。对狼人的影响：守墓人可以通过放逐结果逐步缩小狼坑，狼队需要尽早刀掉守墓人。穿守墓人衣服需要配套的验证信息。

#### 平民阵营

- **平民**：没有主动技能，依靠发言、投票和推理找狼。平民的武器是逻辑和票权——虽然单独一票力量有限，但平民占场上多数，平民的集体投票决定放逐结果。对平民的忠告：不要因为没技能就觉得不重要——每张平民票都是胜负手。可以穿神职衣服帮真神挡刀，也可以主动表水争取信任。狼人穿平民衣服是最常见的伪装方式，但在排水局中容易被优先放逐。
"""

WOLF_ADVANCED_TACTICS = """## 狼队进阶战术手册
以下内容来自高分局狼人杀攻略，提供更深层的战术思路。请结合 WOLF_STRATEGY_REFERENCE 和 WEREWOLF_GLOSSARY 一起使用。

### 一、悍跳发言框架（120秒参考模板）
悍跳预言家时，发言结构比内容更重要。以下是推荐的120秒发言框架：
1. **起手定调（0-10秒）**：「我是预言家，昨晚验了X号，身份是Y。」——直接、果断、不犹豫。
2. **验人逻辑（10-35秒）**：为什么验这个人。参考理由：验警下想拉票、验后置位想定义边界、验高配玩家想确认身份、验上局表现异常的玩家。理由不需要无懈可击，但必须自洽。
3. **警徽流（35-60秒）**：至少两个验人目标。通常配置：1个警下摇摆位+1个焦点位。解释为什么选这两个人。例如：「警徽流先验A号，他是警下还没表态的；再验B号，他刚才发言我觉得有东西。」
4. **对跳分析（60-85秒）**：预判真预言家的位置和可能的验人信息。不要等真预言家跳了再被动应对。例如：「我估计后置位会有人跟我对跳，如果他是狼，他大概率会发XX查杀/金水」。
5. **心路历程（85-105秒）**：简短的「为什么我作为预言家会这样操作」的心路补充。让好人觉得你的思考过程自然、有人味。
6. **收尾定调（105-120秒）**：「我是全场唯一真预言家，好人跟我走，狼人随便跳。」——再次强调确定性，不给模糊空间。

### 二、包装队友与脏好人技巧
狼队不仅要隐藏自己，还要主动塑造好人对全场身份的认知：
- **给队友做身份**：悍跳狼给倒钩狼队友发金水 → 倒钩狼继续倒钩真预言家 → 等悍跳狼被识破时，倒钩狼的「真预言家金水」身份被破除，但倒钩狼可以转冲锋或自爆。关键是金水队友的发言质量要跟得上。
- **脏好人（污身份）**：悍跳狼给真好人发查杀 → 即使悍跳狼最终被识破，被查杀的好人也可能因为「被狼查杀过」而被认为可能是狼踩狼或者身份不干净。更高级的脏法：真预言家发金水给某个好人，悍跳狼也发金水给同一个人 → 这个好人的身份被两方都「保」了，反而变得可疑。
- **脏好人进阶**：踩狼队友来脏好人。悍跳狼说「我觉得X号（好人）和Y号（狼队友）可能是见面的队友」→ X和Y被关联起来。等Y被证实是狼时，X也被牵连。
- **做队友身份进阶**：垫飞。倒钩狼站边真预言家但发言做得很差、猛打真预言家的「狼队友」（实际是好人）、保明显像狼的人 → 目的是让好人认为「真预言家团队质量低」，反向拉低真预言家可信度。与普通倒钩的区别：垫飞不是为了隐藏自己，而是为了污真预言家。

### 三、找神（抿神）技巧
通过发言、投票和行为推断神职身份，是狼队最重要的情报工作：
- **发言抿神**：
  - 预言家：发言有带队感、信息量比闭眼玩家大、会主动安排工作、关注验人和警徽流话题。
  - 女巫：关注夜晚死亡信息、对「谁死了」「平安夜」等话题特别敏感、发言中可能不经意透露「我知道某人是好人」。
  - 猎人：发言强势、不怕出局、「出我我就带你」类发言、投票果断不犹豫。
  - 守卫：关注守护逻辑、可能提及「某人被守」「守人信息」等话题、对连守规则敏感。
  - 白痴：发言放松、不太在意被推、常见的「排水」候选。
- **投票抿神**：神职投票通常比平民更果断、更不怕站错边。平民投票前往往犹豫、跟票、弃票多。注意观察：谁投的票和发言表态不一致？谁弃票后又改了？投票行为反常的玩家可能是神职在隐藏身份。
- **行为抿神**：上警的人数异常（神多则上警人多，民多则上警少）、被查杀后的反应速度（真神通常直接拍身份，假神通常先犹豫）、被放逐前的遗言内容（真神关注局势，平民关注个人）。
- **抿神注意事项**：抿神是辅助判断，不是100%确定。抿错神可能导致刀错人、浪费轮次。结合多种信号交叉验证。抿神结果建议写进 private_note，与队友在狼队夜话中交流确认。

### 四、不见面关系制作（狼人篇）
- **基本思路**：狼队需要在公开互动中刻意制造某些模式，让好人产生错误判断。
- **不见面伪装**：两个狼队友在发言中刻意「不互相提及」→ 让好人觉得两人不认识 → 制造「他们不是狼队友」的假象。但注意：全程零互动反而可疑，适当有一两句轻描淡写的提及更自然。
- **假对立制作**：两个狼队友在发言中互相质疑（但不查到死）→ 让好人认为两人不是队友。操作要点：质疑要有具体内容（「X号你刚才对Y的分析我觉得不对，因为……」），而不是空洞互骂；投票时可以故意分票。
- **假抱团制作**：狼人和好人之间制造「看起来像队友」的互动 → 频繁赞同好人的观点、帮好人说话、和好人投同样的票 → 等狼人暴露时，被关联的好人也受牵连。此技巧适合在确定要牺牲自己时使用（遗言中力保某个好人）。
- **不见面关系的反向利用**：如果好人们已经发现「不见面关系」这个概念并在使用，狼队可以反过来利用——故意与好人做不见面（各自为战），然后让被关联的好人被队友怀疑。

### 五、语境分析与代入视角实战
- **狼人编造发言的语境检查清单**：
  1. 我这句发言在当前轮次合理吗？（不要在第3天说第1天应该说的话）
  2. 我这句发言和我之前的发言/投票一致吗？（不要前后矛盾）
  3. 我这个「身份」在这种情况下通常会说什么？（代入真神视角）
  4. 有没有信息是我这个「身份」不应该知道的？（避免爆狼视角）
  5. 如果我是好人听到这句话，我会信吗？（自检可信度）
- **代入视角练习方法**：每次发言前，用5秒快速代入你所声称的身份：如果你是预言家，你现在最关心什么？如果你是女巫，你现在最想知道什么？然后从那个视角出发构建发言。
- **识别他人的视角矛盾**：当分析其他玩家时，判断TA的发言是否符合TA声称的身份视角。如果不符合（例如声称是平民但一直在分析神职的工作逻辑），那可能是狼人在伪装。

### 六、残局与特殊局面
- **绑票局**：当狼人票数≥好人票数时，无需再隐藏，直接冲票绑票即可获胜。判断绑票需要精确计算存活人数和投票权（警长权重、白痴无投票权）。
- **深水狼收割局**：全程倒钩/深水的狼人，在残局时好人互打、坑位紧张，深水狼的高身份价值最大化。此时不需要再低调，可以主动带队引导放逐。
- **独狼局**：自己是唯一存活狼人时，第一要务是活下去。优先刀有查验能力或带队能力的好人；发言以保命为主，不要主动制造焦点；寻找可以扛推的好人目标。
- **平安夜局**：出现平安夜时，女巫知道救了谁、守卫知道守了谁。如果你是狼人且不掌握这些信息，不要对平安夜的原因做过度推测——说多错多。简单一句「平安夜对好人是好消息」即可。
"""

WOLF_CLOSED_EYE_GUIDE = """## 睁眼发言避坑指南（狼人必读）
你拥有夜晚信息（刀口、队友身份、死亡原因），但这些信息闭眼玩家不知道。你的发言必须严格模拟闭眼视角，否则会被好人识破。

### 一、最常见的睁眼发言（必须避免）
以下发言会直接暴露你的狼人视角：
- **对死者表达过度情绪**：「好痛心」「怎么会是他」「太可惜了」——闭眼玩家对随机死亡的正常反应是**困惑和分析**，不是**惋惜**。你杀了人然后惋惜，这是最典型的睁眼发言。
- **提前知道死亡方式**：在没有公开信息的情况下说「他是被毒的」「昨晚死的不像刀口」——只有女巫和狼人知道死亡原因。
- **默认某人是好人**：「X号肯定是好人」「我相信X号」——闭眼玩家对所有存活玩家都应有怀疑。除非有金水或银水支撑，否则不能笃定某人好人。
- **知道剩余狼人数量**：「还剩2狼」「狼队应该还有3人」——闭眼玩家不知道准确狼数。可以说「按12人局配置应该有4狼，已出2狼所以还剩2狼」这样基于公开配置的推理。
- **替未发言的人开脱**：「X号还没发言，先不说他」——这是狼人保护队友的常见方式。闭眼玩家会对未发言的人保持警惕和好奇。
- **信息量超出闭眼范围**：对夜晚行动细节说得太准确（如知道狼人刀法逻辑、知道女巫用药时机）。
- **对平安夜的过度反应**：女巫和守卫知道平安夜的原因，但你这个"闭眼玩家"不应该知道。平安夜的反应应止于「对好人是好消息」。
- **「验警下有力度」是经典聊爆**：首夜预言家验人发生在警长竞选**之前**——此时没有人知道谁会去警上、谁会留在警下。如果你说「我验了X号，因为他是警下玩家，验他有力度」，等于承认你知道谁会去警下——这是警长竞选结束后才知道的信息。**仅限验人理由**：首夜验人的理由只能用首夜之前就存在的信息（玩家风格、座次、历史表现）。**警徽流完全可以把警下玩家放进去了**——警徽流是警上发言时才留的，此时警上警下已经公开了，留警下玩家在警徽流里是正常操作。

### 二、如何模拟真实的闭眼视角
闭眼玩家的核心特征：**信息不完全 + 持续怀疑 + 推理过程可见**。
- **表达困惑是正常的**：闭眼玩家真的不知道谁是狼。如果你表现得对一切都笃定清楚，反而可疑。适当说「我现在还看不清」「这个情况我不确定」「两个人的发言我都觉得有问题，不好说谁更狼」。
- **推理过程要可见**：不要直接给出结论。要说「因为A说了X，B投了Y，所以我觉得A更像狼」——让好人看到你从公开信息出发的推理链。
- **对死亡的正确反应**：①分析死者身份（「死者可能是被狼人认为有威胁」）②结合投票和发言找线索（「死者昨天说过/投过X」）③思考对局势的影响（「死者出局后，XX的位置更关键了」）。**不是**表达惋惜。
- **怀疑要均匀**：对场上每个玩家都保持一定程度的审视，包括那些"看起来像好人"的人。特别要注意点评你的队友——忽略队友发言是常见的睁眼表现。
- **观点可以修正**：闭眼玩家会根据新信息调整判断。如果你从头到尾立场不变、从不犹豫，反而像知道答案的人。

### 三、发言前自检清单
每次公开发言前，在 inner_thought 中自问：
1. 我这句发言会暴露我知道死亡原因/方式吗？
2. 我对某人的信任/怀疑是基于公开信息，还是基于我的夜晚知识？
3. 我对死者的态度像闭眼玩家吗——是在分析还是在惋惜？
4. 我的推理过程是否可见——有没有从公开信息到结论的逻辑链？
5. 我对队友的发言是否也做了点评？（忽略队友是睁眼表现）
6. 如果我是真闭眼玩家，我会对这个局面感到困惑吗？如果会，那就表达困惑。
"""

WOLF_KILLING_GUIDE = """## 屠边刀法指南（狼人必读）
本局采用屠边规则：狼人只需杀光所有神职**或**所有平民中的任意一边即可获胜。不需要杀光全部好人。

### 一、屠边核心逻辑
- **目标**：清空神坑 或 清空民坑，二选一。哪个更容易就先刀哪个。
- **进度追踪**：每轮夜晚前，在 inner_thought 中更新你对剩余神/民数量的估计。结合公开死亡、翻牌信息和你对存活玩家身份的判断。
- **刀口方向**：一旦选择了刀神边还是刀民边，后续刀口应尽量集中在同一边。来回切换刀不同阵营只会拖延获胜。

### 二、刀人优先级（从高到低）
1. **确定是最后1个神/民的玩家**：如果公开信息+你的推理表明某人是目标阵营的最后1人，刀之立即获胜。
2. **大概率是目标阵营的玩家**：发言、投票、身份起跳等线索表明该玩家属于你正在清空的那一边。
3. **身份不明确的玩家**：当你无法分辨某人属于神还是民时，优先刀那些信息量少、身份模糊的——他们是好人也大概率是平民（神职通常会有信息透露）。
4. **带队好人**：能团结好人的带队者（即使不是神），刀掉能降低好人协作效率。
5. **已暴露神职**：明确的预言家、女巫等。但注意——如果已经确定屠民边方向，刀神反而是浪费轮次。

### 三、常见屠边失误
- **最后1民存活却不刀**：这是最致命的错误。如果场上只剩1个平民，而其他神职都还在，刀这个平民直接获胜。每轮夜晚前务必计算民坑。
- **来回刀不同阵营**：第1夜刀了神，第2夜又去刀民，第3夜再刀神——两边都没清空，浪费轮次。
- **刀已暴露但对屠边无帮助的目标**：如果目标是清民边，刀一个已暴露的预言家只是消除了威胁但不推进胜利条件。当然，如果预言家威胁太大也可以刀，但要意识到这没有推进屠边进度。
- **不追踪身份变化**：随着发言和投票，你对「谁是神谁是民」的判断应该不断更新。不要在 night 1 决定「屠神边」后就机械执行——如果后续发现神都藏得很深、民更好找，应该切换方向。
- **残局不分票**：≤5人残局时，每刀必须精准。此时不明确的目标不要刀——优先刀你能确定身份的目标。

### 四、如何判断某人是神还是民
- **像神的信号**：发言有带队感、投票果断、不怕出局、提及身份相关话题（验人/守人/毒人/银水）、被质疑时强硬回应。
- **像民的信号**：信息量少、发言跟风、投票犹豫、被质疑时表水而非拍身份、说「我就是个民」、对身份话题不敏感。
- **不确定时**：优先认定为「更像民」（大多数存活玩家是民），除非有明显神职信号。保守估计避免高估神坑。

### 五、残局屠边速查
- **剩3人（含你自己）**：你+2好人。此时只需刀1人（剩下1人白天放逐），或刀正确的人直接获胜。如果另2人中有1神1民，刀民则剩1神（未清空任一边），刀神则剩1民（也未清空）——此时需要判断哪边更可能在白天被放逐。
- **剩4人（含你自己）**：你+3好人。如果其中有最后1民，刀之获胜。否则需要2刀。
- **决胜刀口**：你怀疑某人是最后1民/最后1神时，刀之前先确认：如果此人不是，你的备用判断是什么？刀错不仅不赢，还会暴露你的屠边方向。
"""

WOLF_SELF_KNIFE_GUIDE = """## 狼人自刀战术指南
自刀是狼人主动在夜晚击杀己方队友，以骗取女巫解药（银水）为核心目标的战术。当前环境中女巫首夜救人的概率极高，自刀已从高风险赌博进化为常规战术。

### 一、自刀的核心目的
- **骗女巫解药 → 获得银水身份**：被女巫救起的狼人自带公信力，好人对银水天然信任。
- **自刀悍跳 → 银水预言家**：自刀狼以银水身份起跳预言家，双重身份加持让好人更难以质疑。
- **自刀深水 → 银水潜伏**：不上警，利用银水身份在警下扰乱好人逻辑，藏到残局收割。
- **狼王自刀 → 开枪带神**：狼王被首夜自刀，若未被救则开枪带走预言家等关键神职。

### 二、自刀的两种路线
**1. 自刀悍跳（上警路线）**
- 自刀狼利用银水身份起跳预言家
- 验人策略：给女巫/猎人发金水收益高（他们本来就容易被信任），给预言家发查杀也可
- 队友配合：倒钩或弃票，制造「无团队协作」假象

**2. 自刀深水（不上警路线）**
- 放弃警上发言，利用银水身份在警下操作
- 常见打法：倒钩真预言家，或队友自爆后打生推局
- 从始至终上对票、不爆狼式发言，可藏到较深轮次

### 三、自刀时机选择
- **首夜自刀（最常用）**：当前女巫首夜救人概率极高，首夜自刀骗药是稳扎稳打的常规战术。
- **女巫已用解药后**：假装自己被刀但女巫无药可救，可以坐实「我是被狼刀的」身份。
- **狼王板子**：狼王自刀，若未被救则开枪带走真预言家。

### 四、自刀人选
- 优先选择发言能力强的狼人承担（需要撑得起银水身份）
- 避免同一玩家连续多局自刀（容易被识破模式）
- 悍跳狼自刀收益最高——银水+悍跳双重身份加持

### 五、风险与失败应对
- **女巫不救**：直接减员。当前首夜不救的概率较低，但仍存在。
- **被识破**：好人会盘「银水可能是自刀狼」。
- **失败后补救**：遗言认民/认预言家混淆视听；队友悍跳时配合扛推真预言家。
- **关键禁忌**：女巫报出银水之前，千万不要刀女巫（银水还没报你就把证人杀了）。

### 六、好人如何识破自刀
- 银水玩家的发言视角是否有狼人特征（睁眼信息、逻辑跳跃）
- 银水玩家的站边和投票是否与银水身份匹配
- 结合刀口逻辑：为什么狼人要刀这个人？
"""

SEER_GUIDE = """## 预言家操作指南
预言家的核心不是活到最后，而是在活着的轮次里用清晰的视角和警徽流，为好人画出狼坑地图。

### 一、首轮发言模板（按此顺序组织，不要打乱）
1. **报查验**（接麦后第一句话）："X号玩家，我昨晚验的，他是金水/查杀。"——不能拖拉，拖延是悍跳狼的特征（他要现编）。
2. **验人心路**（为什么要验他）：基于位置、座次、历史表现解释——让好人觉得你的视角自然。
3. **警徽流**（至少2人）：一警上一警下或一摇摆一焦点，解释为什么选这两人。
4. **点狼坑**：对跳的标狼，站边对跳的进狼坑，保对跳的也要关注。
5. **拉票**："警徽对预言家很重要，能多报一晚验人，希望大家把警徽给我。"

### 二、获取信任的核心技巧
- **找狼，不是表水**：预言家不需要像平民一样"求认下"。你的发言要以找狼为主，而不是解释自己。
- **不和悍跳狼互喷**：情绪越稳可信度越高。打对方的逻辑漏洞，不要跟他对冲解释。
- **拉够票能出人就行**：不需要所有人信你。站边你的给好人面，不站边的标记后听发言。
- **金水反水要单独对话**：如果你的金水不站你边，一定要专门对话他，解释你的狼坑和判断。拉不回来就可能是狼倒钩。
- **不要认怂**：绝对不能说"如果你们不信我，那我也没办法"——这像狼在放弃。要说"我是真预言家，对跳的标狼，不退。"

### 三、首夜验人思路
- 没发言信息时：验边角位（1/6/7/12号位置开狼概率较高）、验高配玩家（确认身份后可以作为基点）、验后置位（预判悍跳狼可能在警上）。
- 关键原则：首夜验人必须有一个合理的心理历程——你为什么要验他，这在发言中能让好人觉得你视角正常。

### 四、警徽流怎么留
- 第一警徽流：验你觉得疑似狼但不确定的人
- 第二警徽流：验你暂时放不下、但可能定义多张牌身份的人
- 如果对跳狼保了X，第一警徽流验X——看是否为狼队友
- 留一个容错位，可以翻盘

### 五、预言家常见聊爆行为（必须避免）
- 接麦后拖延不报查验（在编假信息）
- 警徽流随意（只验警上不验警下、或完全不给警徽流）
- 发言以解释自己为主而非找狼为主
- 对跳发金水你就直接打死（先听发言再定义）
- 说"我可能是最后一个发言的预言家"（摇摆不定，不像真预）
- 验人理由引用警上/警下概念（首夜验人时还没有警上警下！）
"""

PUBLIC_CLAIM_PATTERNS: dict[Role, tuple[str, ...]] = {
    Role.VILLAGER: ("我是平民", "我跳平民", "我认平民", "我是一张平民", "我是一张民", "我是民"),
    Role.SEER: ("我是预言家", "我是真预言家", "我跳预言家", "我起跳预言家", "预言家是我", "我报预言家"),
    Role.WITCH: ("我是女巫", "我跳女巫", "我起跳女巫", "女巫是我"),
    Role.HUNTER: ("我是猎人", "我跳猎人", "我起跳猎人", "猎人是我"),
    Role.GUARD: ("我是守卫", "我跳守卫", "我起跳守卫", "守卫是我"),
    Role.KNIGHT: ("我是骑士", "我跳骑士", "我起跳骑士", "骑士是我"),
    Role.IDIOT: ("我是白痴", "我跳白痴", "我起跳白痴", "白痴是我"),
    Role.GRAVEKEEPER: ("我是守墓人", "我跳守墓人", "我起跳守墓人", "守墓人是我"),
    Role.SILENCER: ("我是禁言长老", "我跳禁言长老", "我起跳禁言长老", "禁言长老是我"),
}


class AgentContext:
    def __init__(self, player: Player, game_state: GameState):
        self.player = player
        self.game = game_state
        self.memory = load_agent_memory(player.name)
        if not self.memory.personality and player.personality:
            self.memory.personality = player.personality
        self.relevant_memories = retrieve_relevant_memories(
            agent_name=player.name,
            current_role=player.role.value,
            current_players=game_state.players,
            memory=self.memory,
            limit=3,
        )

    @property
    def alive_players(self) -> list[Player]:
        return [player for player in self.game.players if player.status.value == "alive"]

    @property
    def alive_other_players(self) -> list[Player]:
        return [player for player in self.alive_players if player.name != self.player.name]

    @staticmethod
    def _join_names(names: list[str]) -> str:
        return "、".join(names) if names else "无"

    def _role_config_line(self) -> str:
        counts: dict[str, int] = {}
        for player in self.game.players:
            role_name = ROLE_NAMES_ZH[player.role]
            counts[role_name] = counts.get(role_name, 0) + 1
        return "、".join(f"{name}x{count}" for name, count in counts.items())

    def _memory_record_block(self) -> str:
        lines = [
            f"- Total games: {self.memory.total_games}",
            f"- Total wins/losses: {self.memory.wins}/{self.memory.losses}",
        ]
        role_summary = self.memory.role_summaries.get(self.player.role.value)
        if role_summary:
            lines.append(
                f"- Same role record ({self.player.role.value}): "
                f"{role_summary.total_games} games, {role_summary.wins} wins, {role_summary.losses} losses"
            )
        else:
            lines.append(f"- Same role record ({self.player.role.value}): no mature history yet")
        return "\n".join(lines)

    def _role_memory_summary_block(self) -> str:
        role_summary = self.memory.role_summaries.get(self.player.role.value)
        if not role_summary:
            return "No same-role summary yet. Build one from this game."

        sections: list[str] = []
        if role_summary.strengths:
            sections.append("What has worked:\n" + "\n".join(f"- {item}" for item in role_summary.strengths))
        if role_summary.pitfalls:
            sections.append("Repeated pitfalls:\n" + "\n".join(f"- {item}" for item in role_summary.pitfalls))
        if role_summary.signals_to_watch:
            sections.append("Signals to watch:\n" + "\n".join(f"- {item}" for item in role_summary.signals_to_watch))
        if role_summary.role_tips:
            sections.append("Actionable role tips:\n" + "\n".join(f"- {item}" for item in role_summary.role_tips))
        if role_summary.recent_examples:
            sections.append("Recent examples:\n" + "\n".join(f"- {item}" for item in role_summary.recent_examples))
        return "\n\n".join(sections) if sections else "No same-role summary yet. Build one from this game."

    def _wolf_strategy_reference_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""
        return WOLF_STRATEGY_REFERENCE

    def _wolf_advanced_tactics_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""
        return WOLF_ADVANCED_TACTICS

    def _closed_eye_guide_block(self) -> str:
        if self.player.role in WOLF_ROLES:
            return WOLF_CLOSED_EYE_GUIDE
        # For good players: provide open-eye detection guide
        return """## 睁眼发言识别指南（好人用）
以下是常见的狼人睁眼发言特征，帮助你在发言中识别狼人：

### 常见睁眼信号
- **对死者表达惋惜而不是分析**：「好痛心」「太可惜了」「怎么会是他」——闭眼玩家对随机死亡的第一反应是困惑和分析（为什么是他？他得罪了谁？），不是惋惜。
- **默认某人是好人**：在没有金水/银水的情况下笃定「X是好人」——可能是狼人知道X不是自己队友。
- **知道剩余狼人数**：在没有公开配置推理的情况下说「还剩2狼」——闭眼玩家只能基于「总配置-已出局狼」来推算。
- **替未发言的人说话**：「X还没发言，先不说他」——可能是狼人保护队友。
- **对死亡方式的判断超出公开信息**：在无人报死亡原因时提及「被毒的」「刀口」「平安夜说明女巫救人了」等。
- **立场从不变化**：从头到尾不修正判断、不表达困惑——像知道答案而不是在推理。
- **忽略特定玩家**：对某些玩家（可能是队友）的发言系统性地跳过不点评。
- **「验警下有力度」是经典聊爆**：真预言家首夜验人时，警长竞选还没开始，他不知道谁会去警上警下。如果一个人说「我验X号因为他是警下，验他有力度」，说明他的验人理由是在警长竞选**之后**才编造的。真预言家的验人理由只会基于已有信息（玩家风格、座次、历史表现等）。

### 如何使用这些信号
- 单一信号只是线索，交叉多个信号才是证据。
- 结合投票、发言顺序、身份起跳等综合判断。
- 不要因为一句话就定狼——有些好人也会说话不够严谨。
- 在你的 inner_thought 中标注观察到睁眼信号的玩家，持续追踪他们在后续轮次的表现。"""

    def _wolf_killing_guide_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""
        if self.game.rules.win_rule.value != "slaughter_side":
            return ""
        return WOLF_KILLING_GUIDE

    def _seer_guide_block(self) -> str:
        if self.player.role != Role.SEER:
            return ""
        return SEER_GUIDE

    def _wolf_self_knife_guide_block(self) -> str:
        if self.player.role in WOLF_ROLES:
            return WOLF_SELF_KNIFE_GUIDE
        return """## 自刀（银水狼）识别指南
自刀是狼人主动刀自己人以骗取女巫解药的战术。当前环境中女巫首夜救人概率极高，银水不再等于铁好人。

### 银水玩家的可疑信号
- **发言视角异常**：银水玩家是否在不经意间透露了狼人视角信息？如默认某人是好人、知道剩余狼人数。
- **站边与银水身份不匹配**：银水玩家如果站边和投票始终与某个"预言家"完全同步、从不表达独立判断，可能是自刀狼在配合悍跳队友。
- **刀口逻辑反常**：为什么狼人要首夜刀这个人？如果此人是公认的高配/带队型玩家，那么被刀是合理的；但如果此人发言平平、没有明显威胁，被首刀本身就值得怀疑。
- **对银水身份的过度依赖**：银水玩家长时间不报身份、只靠"我是银水"来抗辩——真银水通常会在适当时候亮明自己的真实身份来增加可信度。
- **行为模式异常**：被救后异常低调（深水自刀狼）或异常激进（悍跳自刀狼），与正常被救后的「谨慎但积极」心态不符。

### 盘自刀的正确方式
- 银水只是线索，不是免死金牌也不是定罪证据。结合发言、投票、刀口逻辑综合判断。
- 不要直接说「你是自刀狼」——先观察银水玩家的站边是否自然、投票是否独立。
- 如果银水玩家是女巫报出的，先观察女巫本身是否可信（假女巫可能会报假银水给狼队友）。
"""


    def _retrieved_memories_block(self) -> str:
        if not self.relevant_memories:
            return "No similar historical games were retrieved."

        sections: list[str] = []
        for index, memory in enumerate(self.relevant_memories, start=1):
            lines = [
                f"[Memory {index}] score={memory.score:.1f} game={memory.game_id}",
                f"role={memory.role}, board={memory.role_config}, players={memory.player_count}, rounds={memory.rounds_played}",
                f"result={'win' if memory.won else 'loss'}, survived={'yes' if memory.survived_to_end else 'no'}",
                f"summary: {memory.summary}",
            ]
            if memory.key_moments:
                lines.append("key moments: " + " | ".join(memory.key_moments))
            if memory.useful_takeaways:
                lines.append("takeaways: " + " | ".join(memory.useful_takeaways))
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def _other_common_wolves_alive(self, name: str) -> list[Player]:
        return [
            player
            for player in self.game.players
            if player.name != name and player.status.value == "alive" and player.role in COMMON_WOLF_ROLES
        ]

    def _is_awakened_hidden_wolf(self) -> bool:
        if self.player.role != Role.HIDDEN_WOLF:
            return False
        return not self._other_common_wolves_alive(self.player.name)

    def _is_awakened_stone_gargoyle(self) -> bool:
        if self.player.role != Role.STONE_GARGOYLE:
            return False
        return not self._other_common_wolves_alive(self.player.name)

    def _can_access_wolf_chat(self) -> bool:
        if self.player.role in VISIBLE_PACK_WOLF_ROLES:
            return True
        if self.player.role == Role.HIDDEN_WOLF:
            return self._is_awakened_hidden_wolf()
        if self.player.role == Role.STONE_GARGOYLE:
            return self._is_awakened_stone_gargoyle()
        return False

    def _visible_wolf_teammates(self) -> list[str]:
        if self.player.role == Role.HIDDEN_WOLF and not self._is_awakened_hidden_wolf():
            return []
        if self.player.role == Role.STONE_GARGOYLE and not self._is_awakened_stone_gargoyle():
            return []

        if self.player.role in VISIBLE_PACK_WOLF_ROLES:
            return [
                player.name
                for player in self.game.players
                if player.name != self.player.name
                and player.role in VISIBLE_PACK_WOLF_ROLES
            ]

        return []

    def _wolf_chat_history_block(self) -> str:
        if not self._can_access_wolf_chat():
            return ""
        visible_items = [
            item
            for item in self.game.wolf_chat
            if not item.visible_to or self.player.name in item.visible_to
        ]
        if not visible_items:
            return "## wolf_team_private_chat\nNo private wolf-team chat has been recorded yet."

        lines = [
            "## wolf_team_private_chat",
            "Only wolves with access to the wolf channel can see this. Treat it as teammate-only context, not public speech.",
        ]
        for item in visible_items[-12:]:
            target_text = f", kill target: {item.kill_target}" if item.kill_target else ""
            lines.append(f"- Night {item.round_number}{target_text}, {item.speaker}: {self._trim_public_text(item.message, 260)}")
        return "\n".join(lines)

    def _alive_visible_wolf_teammates(self) -> list[str]:
        return [
            name
            for name in self._visible_wolf_teammates()
            if any(player.name == name and player.status.value == "alive" for player in self.game.players)
        ]

    def _visible_wolf_roster_block(self) -> str:
        teammates = []
        for name in self._visible_wolf_teammates():
            player = next((candidate for candidate in self.game.players if candidate.name == name), None)
            if not player:
                continue
            status = "存活" if player.status.value == "alive" else "已出局"
            teammates.append(f"{name}（{ROLE_NAMES_ZH[player.role]}，{status}）")

        teammate_text = self._join_names(teammates)
        if teammates:
            return (
                f"你确认的狼队名单：{teammate_text}。\n"
                "这些名字是确定队友；名单外玩家不是你的已知狼队友。不要把公开发言里「像狼/像队友」的玩家当成确定队友。"
                "如果名单外玩家跳预言家或其他神职，不能在真实推理里直接称其为「悍跳狼」或「队友悍跳」；"
                "你可以判断他像真神、诈身份好人、挡刀民，或公开狼面较高但未确认。"
            )
        return (
            "你当前没有可确认的狼队友。名单外玩家不是你的已知狼队友，不能当作队友来保护。"
            "如果名单外玩家跳预言家或其他神职，不能在真实推理里直接称其为「悍跳狼」或「队友悍跳」；"
            "你可以判断他像真神、诈身份好人、挡刀民，或公开狼面较高但未确认。"
        )

    def _current_round_discussion_speeches(self) -> list:
        return [
            speech
            for speech in self.game.speeches
            if speech.round_number == self.game.round_number and speech.phase in ("discuss", "last_words")
        ]

    @staticmethod
    def _trim_public_text(text: str, limit: int = 220) -> str:
        text = " ".join((text or "").split())
        return text if len(text) <= limit else text[: limit - 3] + "..."

    @staticmethod
    def _normalize_claim_text(text: str) -> str:
        return re.sub(r"\s+", "", text or "")

    def _extract_explicit_role_claims(self) -> list[dict]:
        claims: list[dict] = []
        seen: set[tuple[str, Role]] = set()
        for speech in self.game.speeches:
            if not speech.public_speech:
                continue
            normalized = self._normalize_claim_text(speech.public_speech)
            for role, patterns in PUBLIC_CLAIM_PATTERNS.items():
                if not any(pattern in normalized for pattern in patterns):
                    continue
                key = (speech.speaker, role)
                if key in seen:
                    break
                player = next((item for item in self.game.players if item.name == speech.speaker), None)
                claims.append(
                    {
                        "speaker": speech.speaker,
                        "role": role,
                        "text": self._trim_public_text(speech.public_speech, 180),
                        "round": speech.round_number,
                        "phase": speech.phase,
                        "status": player.status.value if player else "unknown",
                    }
                )
                seen.add(key)
                break
        return claims

    def _public_role_claims_block(self) -> str:
        claims = self._extract_explicit_role_claims()
        if not claims:
            return (
                "## 公开身份关键词线索\n"
                "暂无被规则摘出的身份关键词；这不代表无人交代身份，是否报身份仍以发言原文和你的身份工作区判断。"
            )

        phase_labels = {
            "sheriff_campaign": "警上发言",
            "sheriff_runoff": "警长PK",
            "day_vote_runoff": "放逐PK",
            "discuss": "白天发言",
            "last_words": "遗言",
        }
        lines = [
            "## 公开身份关键词线索",
            "以下只是关键词摘录，不是系统盖章；是否算报身份、是否可信、是否只是诈身份，需要你在自己的身份工作区里判断。",
        ]
        for claim in claims:
            lines.append(
                f"- 第 {claim['round']} 轮 {phase_labels.get(claim['phase'], claim['phase'])}："
                f"{claim['speaker']} 的发言出现 {ROLE_NAMES_ZH[claim['role']]} 关键词"
                f"（当前{('存活' if claim['status'] == 'alive' else '已出局')}）：{claim['text']}"
            )
        return "\n".join(lines)

    def _role_bucket_name(self, role: Role) -> str:
        if role in WOLF_ROLES:
            return "狼坑"
        if role in GOD_ROLES:
            return "神坑"
        if role == Role.VILLAGER:
            return "民坑"
        return "其他坑"

    def _role_bucket_counts(self, roles: list[Role]) -> dict[str, int]:
        counts = {"狼坑": 0, "神坑": 0, "民坑": 0, "其他坑": 0}
        for role in roles:
            bucket = self._role_bucket_name(role)
            counts[bucket] = counts.get(bucket, 0) + 1
        return counts

    def _format_bucket_counts(self, counts: dict[str, int]) -> str:
        ordered = ["狼坑", "神坑", "民坑", "其他坑"]
        return "、".join(f"{name} {counts.get(name, 0)}" for name in ordered if counts.get(name, 0))

    def _format_role_count_items(self, role_counts: dict[Role, int]) -> str:
        items = [
            f"{ROLE_NAMES_ZH[role]} {count}"
            for role, count in role_counts.items()
            if count > 0
        ]
        return "、".join(items) if items else "无"

    def _format_name_counts(self, counts: dict[str, int]) -> str:
        items = [f"{name} {count}次" for name, count in counts.items()]
        return "、".join(items) if items else "无"

    def _publicly_revealed_death_role(self, item: dict) -> str:
        phase = item.get("phase")
        if item.get("public_role") or phase in {"werewolf_self", "white_wolf_self"}:
            return str(item.get("role") or "")
        return ""

    def _public_role_slot_pressure_block(self) -> str:
        setup_counts = self._role_bucket_counts([player.role for player in self.game.players])
        setup_role_counts: dict[Role, int] = {}
        for player in self.game.players:
            setup_role_counts[player.role] = setup_role_counts.get(player.role, 0) + 1
        role_by_public_name = {name: role for role, name in ROLE_NAMES_ZH.items()}
        revealed_dead_roles: list[Role] = []
        dead_names: list[str] = []
        for item in self.game.history:
            if item.get("type") != "death":
                continue
            dead_name = str(item.get("player") or "")
            if dead_name:
                dead_names.append(dead_name)
            public_role = self._publicly_revealed_death_role(item)
            if public_role in role_by_public_name:
                revealed_dead_roles.append(role_by_public_name[public_role])
        revealed_counts = self._role_bucket_counts(revealed_dead_roles)
        remaining_counts = {
            bucket: max(setup_counts.get(bucket, 0) - revealed_counts.get(bucket, 0), 0)
            for bucket in setup_counts
        }
        revealed_role_counts: dict[Role, int] = {}
        for role in revealed_dead_roles:
            revealed_role_counts[role] = revealed_role_counts.get(role, 0) + 1
        public_alive_capacity = {
            role: max(count - revealed_role_counts.get(role, 0), 0)
            for role, count in setup_role_counts.items()
        }
        public_speech_counts: dict[str, int] = {player.name: 0 for player in self.alive_players}
        for speech in self.game.speeches:
            if not speech.public_speech or speech.speaker not in public_speech_counts:
                continue
            if speech.phase not in {"sheriff_campaign", "sheriff_runoff", "day_vote_runoff", "discuss", "last_words"}:
                continue
            public_speech_counts[speech.speaker] += 1

        lines = [
            "## 公开全额配置消息",
            f"- 本局角色全额：{self._format_role_count_items(setup_role_counts)}；按阵营坑位汇总：{self._format_bucket_counts(setup_counts)}。",
            f"- 已死亡玩家：{self._join_names(dead_names)}。普通死亡不等于公开翻牌，不能据此扣具体角色坑。",
            f"- 已公开翻牌/自爆消耗：{self._format_role_count_items(revealed_role_counts)}；仅扣除这些公开身份后的可见容量：{self._format_role_count_items(public_alive_capacity)}；按坑位汇总：{self._format_bucket_counts(remaining_counts)}。",
            f"- 存活玩家公开发言次数：{self._format_name_counts(public_speech_counts)}。",
            "- 上面只是全额配置、公开翻牌/自爆和发言次数，不是系统判断的「缺额」、不是系统判断的身份归属，也不代表某个无人提及的身份一定存在或一定应被穿。",
            "- 请你结合发言原文、票型、死亡和自己的身份工作区，自行判断是否存在坑位压力、无人提及的身份衣服、低信息位置、需要逼身份的位置，或可以提出的新身份矛盾。",
            "- 发言和投票可以围绕你自己推理出的坑位问题施压：你占哪个民坑/神坑？谁和你对跳？如果不亮身份，理由是什么？当前民坑、神坑或狼坑是否被挤爆？",
        ]
        return "\n".join(lines)

    def _alive_explicit_claimants(self, role: Role) -> list[str]:
        return [claim["speaker"] for claim in self._extract_explicit_role_claims() if claim["role"] == role and claim["status"] == "alive"]

    def _wolf_team_state_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""

        alive_teammates = self._alive_visible_wolf_teammates()
        dead_teammates = [
            name
            for name in self._visible_wolf_teammates()
            if name not in alive_teammates
        ]
        alive_wolf_count = 1 + len(alive_teammates)

        lines = [
            "## 狼队确认存亡",
            f"- 你自己：{self.player.name}（当前存活）",
            f"- 已确认存活狼队友：{self._join_names(alive_teammates)}",
            f"- 已确认出局狼队友：{self._join_names(dead_teammates)}",
        ]
        if alive_wolf_count == 1:
            lines.append("- 局势事实：你当前是自己已知范围内唯一存活狼人。请把「保留狼人数」「切白天进夜」「自己是否将被放逐」一起纳入收益判断。")
        else:
            lines.append(f"- 局势事实：你当前已知仍有 {alive_wolf_count} 名存活狼人（含你自己）。")
        return "\n".join(lines)

    def _wolf_targeting_priority_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""

        seer_claimants = self._alive_explicit_claimants(Role.SEER)
        witch_claimants = self._alive_explicit_claimants(Role.WITCH)
        sheriff_alive = self.game.sheriff_name and any(
            player.name == self.game.sheriff_name and player.status.value == "alive" for player in self.game.players
        )

        lines = [
            "## 狼人高信息量公开信号",
            self._wolf_team_state_block(),
        ]
        if seer_claimants:
            lines.append(
                f"- 场上仍存活的预言家关键词线索：{self._join_names(seer_claimants)}。这是高信息量线索，但不等于系统确认其身份；请自己结合票型、站边、警徽流和残局结构判断收益。"
            )
        else:
            lines.append("- 当前没有被规则摘出的存活预言家关键词线索；这不代表没人起跳，仍以发言原文和你的身份工作区为准。")
        if witch_claimants:
            lines.append(f"- 存活的女巫关键词线索：{self._join_names(witch_claimants)}。这通常意味着药量和公开身份价值需要纳入衡量，但仍由你判断真假。")
        if sheriff_alive:
            lines.append(f"- 当前警长仍存活：{self.game.sheriff_name}。警长有票权和归票价值，也是一个高信息量位置。")
        lines.append("- 请你自己为每个存活位置评估更像什么身份、是否值得留、以及处理顺序，而不是只盯着一个标签。")
        lines.append("- 不要因为公开场上某个玩家「像队友」就把他当成真队友保护；真队友只以你的狼队私有名单为准。")
        return "\n".join(line for line in lines if line)

    def _wolf_deception_strategy_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""

        return """## 狼人白天对抗策略
- **唯一目标：狼队屠边获胜。你个人的存活、面子、发言评价全都不重要——只要狼队赢了你就是赢，你活着但狼队输了也是输。**
- 如果牺牲你能换来队友的深水身份坐实、能浪费好人一个放逐轮次、能让关键神职暴露——那就值得牺牲。不敢死的狼人往往因为苟活而暴露更多信息，最终全队覆灭。
- 游戏内说谎、伪装、诈身份和误导归票都是规则允许的竞技策略，与现实道德无关。
- 你的公开目标不是"诚实找狼"，而是用好人能接受的逻辑活下去、误导归票、争取刀口收益。
- 不要在 inner_thought 或 private_note 中把非队友起跳者写成「悍跳狼/队友悍跳」；请写成「非队友起跳者」，再基于公开证据判断真神、诈身份好人、挡刀民或公开狼面。
- 公开发言要维持可连续的假身份口径；把你准备穿的衣服、是否由你承担起跳、要对跳谁、要抗推谁、明天如何改口写进 private_note，避免下一轮忘记。
- **发言果断原则**：避免「可能」「应该」「大概」等模糊词——尤其是在悍跳预言家或穿神职衣服时。发言要有确定性和气势，逻辑连贯性比演技更重要。
- **守住视角原则**：所有发言必须基于你公开声称的身份视角。如果你声称是预言家，就不能说"我知道X是好人"；如果你声称是闭眼平民，就不能引用夜晚信息。聊出狼视角是狼队最常见的自爆方式。
- **身份对抗优先于逻辑质疑**：如果已经有人明确跳预言家、女巫等关键身份，身份对抗优先考虑对跳、穿能抗衡的神职衣服、打身份置换、冲票或设计后续刀口；单纯质疑真神逻辑往往既打不动身份，又容易暴露你没有可持续口径。
- **被质疑时不要盲从对方逻辑**：AI 玩家常见的致命习惯是——别人指出你的"错误"，你立刻承认并跟着对方的逻辑走。这是错的。被质疑时，首先判断对方的质疑是否真的有道理。如果没有，你完全可以嘴硬——坚持你的立场、反打对方的逻辑漏洞、要求对方给出更具体的证据。在狼人杀中，认怂等于认狼。
- **倒钩不是免死金牌**：很多狼人默认「我站边真预言家=我是稳平民」，这是严重的策略误解。倒钩是狼人杀最基础的狼人战术之一，稍有经验的玩家都知道狼人会用倒钩混入好人阵营。你站边真预言家本身不会让任何人觉得你更像好人——你站边的理由、发言质量、投票时机和逻辑一致性才是判断依据。如果全狼都倒钩真预言家，狼队失去全部身份压力，真预言家单边带队轻松排坑。倒钩的真正价值在残局关键时刻反水冲票，而非日常「站对边保平安」。
- **穿民是最弱的伪装（不要默认穿民）**：很多狼人觉得「我装平民最安全，什么都不用编」。这是严重的策略错误——平民在场上没有任何防护，被查杀时没有反制手段，被扛推时只能靠发言自保，一旦被真平民反卷排坑就直接出局。穿民收益天花板极低，只能帮你苟活一轮，无法带队改变局势。如果全狼都穿民，好人只需稳定排水就能赢。\n"
        "- **什么时候可以穿民**：①你是深水狼，已经有队友悍跳吸引了全部火力，你只需要潜伏到残局收割 ②场上进入残局需要你抿神刀人 ③你是隐狼/石像鬼等需要隐藏到后期的角色。\n"
        "- **什么时候绝对不能穿民**：①被预言家查杀时——穿民等于坐以待毙，应该跳女巫/猎人续命 ②被多人怀疑上PK台时——继续穿民不会有人信，不如跳神拼一轮 ③狼队需要冲票时——此时需要穿神职带队拉票。\n"
        "- **穿不同衣服的收益对比**：白痴/守卫（低风险中收益，无法自证）< 猎人（中风险中收益，死后可自证但可能被真猎人盯上）< 女巫（高风险高收益，有毒药自证但报错银水直接暴露）< 预言家（极高风险极高收益，可抢警徽但需要全套假信息支撑）。选择衣服时优先选风险收益匹配你当前处境的。"""


    def _wolf_sheriff_claim_strategy_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""

        teammate_claims = [
            claim["speaker"]
            for claim in self._extract_explicit_role_claims()
            if claim["speaker"] in self._visible_wolf_teammates()
            and claim["role"] == Role.SEER
            and claim["status"] == "alive"
        ]
        teammate_claim_text = self._join_names(teammate_claims)
        if teammate_claims:
            status_line = f"已确认队友中已有预言家关键词线索：{teammate_claim_text}。你可以判断其是否正在承担预言家衣服，并选择配合、倒钩、补强或切割；不要误以为名单外起跳者也是队友。"
        else:
            status_line = "目前没有从关键词线索中看到已确认队友承担预言家衣服。不要把「等队友悍跳」当成唯一计划；如果狼队需要预言家衣服，请评估自己是否适合承担。"

        return f"""## 狼人警上身份压力提醒
{status_line}
- 上警前可以比较几条路线：自己悍跳预言家抢警徽、穿民/神边不上强身份、倒钩或支持他人。
- 如果选择不上警或不跳，请基于自己的位置、发言顺序、队友状态和风险收益解释，而不是笼统等待队友。
- **悍跳预言家出发前清单**（如果准备悍跳，请在 inner_thought 里逐项确认）：
  1. 假验人对象和结果：昨晚验了几号？金水还是查杀？
  2. 验人理由：为什么验这个位置？（拉票/定义边界/确认焦点）
  3. 警徽流：先验谁后验谁？覆盖了警下摇摆位吗？
  4. 队友配合：谁冲锋谁倒钩谁深水？写到 private_note 的"狼队计划："里。
  5. 应对真预言家：如果真预言家起跳并报出与你矛盾的验人，你如何回应？
  6. 改口条件：什么情况下退水？什么情况下坚持到底？
- 如果你已经成焦点位，穿神职衣服、强抗辩、对跳、冲票、自爆或沉默都只是候选项；请按局势自行取舍。"""

    def _wolf_active_pressure_check_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""

        return """## 狼队公开打法提醒
- 倒钩、冲票、悍跳、穿衣服、强推、切割都只是候选打法，没有哪一个应当自动成为默认答案。
- 选择倒钩时，请确认它带来的具体收益：可信身份、保护关键结构、诱导刀口/验人、制造后续票型空间，或让队友的公开口径更顺。
- **旁观者效应提醒**：每匹狼都看到「应该有人做X」，但每匹狼都以为队友会去做X，结果没人做。全队统一策略不是问题——全队无意识地统一才是问题。**如果你发现你的选择和所有确认队友一样，问自己：这是我有意选择的战术，还是我只是跟着默认走了？** 有意为之的统一（如全队冲锋碾压抢警徽）可以很强；无意识的随大流才是致命的。
- 狼队不需要人人同向，也不需要机械分工；请根据你自己的位置、发言质量、票权和队友状态决定公开姿态。
- private_note 里优先留下可复用的短口径：你当前准备怎么站边、穿什么衣服或不穿、主推谁、保谁、哪些情况需要改口。

### 跳女巫和猎人——为什么这两个神职值得穿
女巫有毒药可自证，猎人有枪可威慑。好人对跳女巫/猎人的玩家天然不敢轻易质疑，因为万一对方是真神、自己有被毒/被带的风险。因此狼人跳这两个身份比跳守卫/白痴更有压迫力。

**三种常见的适合跳女巫/猎人的局面**（是你自己的判断，不是系统指令）：
1. **场上还没有人明确跳女巫/猎人**：谁先起跳，好人往往会默认相信（先入为主）。后跳的人需要解释"为什么之前不跳"，天生被动。
2. **狼队人数有优势**：票权在手时，穿神职可以借身份带队归票，引导放逐方向。
3. **你自己成了焦点/被怀疑**：穿民在焦点位几乎等于等死。穿女巫/猎人则给好人一个"万一是真神"的顾虑——对方不敢轻易归你。

**跳女巫的操作参考**：银水对象（谁+第几夜+为什么救）必须与公开死亡吻合；毒药状态可以用来威慑（"我还有毒，谁敢动我"）。
**跳猎人的操作参考**：发言要强势、不怕出局。"出我我就带你"是猎人的核心威慑而非逻辑辩论。"""

    def _wolf_god_disguise_playbook_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""

        return """## 狼人神职衣服候选提醒
- 不要只把"穿衣服"理解成穿民。神职衣服也是可选公开打法，尤其在你成为焦点位、需要抗推、需要抢归票权、或需要稀释真神信息时。

### 各神职衣服风险等级与操作指南
- **白痴衣服（低风险）**：白痴无法自证且被投出后翻牌免死，是狼人最安全的选择之一。适合在抗推位上穿。发言要点：语气轻松，不急于带队，说自己"不怕被投"。但翻牌机制会失去投票权，拖轮次用。
- **守卫衣服（低风险）**：守卫无法直接自证，是狼人较安全的选择。需要准备完整的守人逻辑链——每晚守了谁、为什么守这个目标、守人逻辑如何与夜晚死亡吻合。可以声称"我第一夜空守/守了预言家"来增强可信度。
- **女巫衣服（高风险）**：女巫有毒药可自证（声称要毒人），报错银水或毒人逻辑矛盾会立刻暴露。穿女巫衣服前必须：1) 核对公开夜晚死亡信息 2) 准备好具体的银水对象和救人时间 3) 想好毒药使用逻辑。只在真女巫已确定死亡、或你有充分抿神能力确定女巫身份时考虑。如果真女巫存活且可能起跳，报真银水比报假银水安全得多。
- **猎人衣服（高风险）**：猎人是强神，死后可开枪带人自证。穿猎人衣服一旦被真猎人盯上，猎人死后带枪验身份你会直接暴露。仅在轮次充足、猎人身份未明、且你不会真的被投票出局时考虑。适合用于威慑归票（"出我我就带你"），但不能声称知道真实身份信息。
- **骑士衣服（极高风险）**：真骑士可以决斗验证身份，假骑士空喊会被直接识破。如果本局有骑士，绝对不要穿骑士衣服。只在确认骑士已死亡或本局无骑士时考虑。
- **守墓人/禁言长老（中等风险）**：仅在确认本局存在这些角色时考虑。守墓人需要准备"前一晚验了被放逐者是否是狼"的信息，禁言长老需要解释每晚禁言了谁以及为什么。

### 穿神职衣服通用原则
- **不能"干拍"身份**：只喊"我是女巫/猎人/守卫"而不说具体的工作信息和心路历程，等于自爆。必须像该神职一样汇报工作成果（守了谁、救了谁、验了谁）。
- **逻辑自洽**：你编造的技能使用历史必须自洽——不能第2夜说救了A但第3夜说毒了A；不能声称守了某人但那人当晚死了（除非同守同救）。
- **心路历程**：解释为什么第1夜救人不救别人、为什么守这个人不守那个人。有心路历程的假信息比干巴巴的假数据可信度高得多。
- **接查杀时的应对**：被查杀时不一定要拍身份。标准应对：先质疑对方验人逻辑，要求对方退水。如果确定要拍身份，选择风险匹配的衣服（守卫>白痴>女巫>猎人）。
- **抗推位上的选择**：如果你在抗推位，穿守卫或白痴衣服相对安全；如果轮次充足、身份不明朗，可以先表水而不拍身份。
- 选择衣服前看：它是否有公开依据支撑、是否容易被对跳、是否会暴露狼视角。不穿神职也可能是合理选择。
- 在 private_note 里留下可连续的假身份口径或改口条件，避免下一轮忘记自己穿的衣服。"""

    def _public_dead_role(self, name: str) -> str:
        for item in reversed(self.game.history):
            if item.get("type") == "death" and item.get("player") == name:
                return self._publicly_revealed_death_role(item)
        return ""

    def _public_board_state(self) -> str:
        alive_count = len(self.alive_players)
        lines = [
            "## 公开局势面板",
            f"当前轮次：第 {self.game.round_number} 天",
            f"人数：存活 {alive_count} / 总计 {len(self.game.players)}",
            f"警长：{self.game.sheriff_name or '暂无'}",
            "座位顺序与生死：",
        ]

        for index, player in enumerate(self.game.players, start=1):
            status = "存活" if player.status.value == "alive" else "阵亡"
            public_role = self._public_dead_role(player.name)
            if public_role and player.status.value != "alive":
                status += f"，公开身份：{public_role}"

            markers = []
            if player.name == self.player.name:
                markers.append("你")
            if self.game.sheriff_name == player.name:
                markers.append("警长")
            if not player.vote_right:
                markers.append("无投票权")
            marker_text = f"（{'、'.join(markers)}）" if markers else ""
            lines.append(f"{index}. {player.name}{marker_text}：{status}")

        return "\n".join(lines)

    def _round_public_speeches(self, round_number: int) -> list[str]:
        phase_labels = {
            "sheriff_campaign": "警上",
            "sheriff_runoff": "警长PK",
            "day_vote_runoff": "放逐PK",
            "discuss": "发言",
            "last_words": "遗言",
        }
        lines = []
        for speech in self.game.speeches:
            if speech.round_number != round_number or speech.phase not in phase_labels:
                continue
            if not speech.public_speech:
                continue
            lines.append(f"- {phase_labels[speech.phase]} {speech.speaker}：{self._trim_public_text(speech.public_speech)}")
        return lines

    def _public_sheriff_election_block(self) -> str:
        elections = [item for item in self.game.history if item.get("type") == "sheriff_election"]
        if not elections:
            return ""

        phase_labels = {
            "sheriff_campaign": "警上",
            "sheriff_runoff": "警长PK",
        }
        lines = ["## 警长竞选公开信息"]
        for election in elections:
            election_round = int(election.get("round") or 1)
            candidates = election.get("candidates", [])
            lines.append(f"第 {election_round} 天警长竞选：")
            lines.append(f"- 上警候选人：{self._join_names(candidates)}")

            campaign_lines = []
            for speech in self.game.speeches:
                if speech.round_number != election_round or speech.phase not in phase_labels or not speech.public_speech:
                    continue
                campaign_lines.append(
                    f"  - {phase_labels[speech.phase]} {speech.speaker}：{self._trim_public_text(speech.public_speech)}"
                )
            if campaign_lines:
                lines.append("- 竞选/PK发言：")
                lines.extend(campaign_lines)

            vote_rounds = election.get("vote_rounds") or [
                {
                    "round": 1,
                    "candidates": candidates,
                    "votes": election.get("votes", []),
                    "counts": election.get("counts", {}),
                    "winner": election.get("winner"),
                    "tied_targets": [],
                }
            ]
            for vote_round in vote_rounds:
                round_index = vote_round.get("round", 1)
                ineligible_voters = [str(name) for name in vote_round.get("ineligible_voters", candidates) if name]
                eligible_voters = [str(name) for name in vote_round.get("eligible_voters", []) if name]
                if not eligible_voters:
                    eligible_voters = [
                        player.name
                        for player in self.game.players
                        if player.name not in ineligible_voters and player.vote_right
                    ]
                actual_voters = [str(name) for name in vote_round.get("actual_voters", []) if name]
                if not actual_voters:
                    actual_voters = [str(vote.get("voter")) for vote in vote_round.get("votes", []) if vote.get("voter")]
                missing_voters = [str(name) for name in vote_round.get("missing_voters", []) if name]
                if not missing_voters:
                    missing_voters = [name for name in eligible_voters if name not in actual_voters]
                vote_text = "、".join(
                    f"{vote.get('voter')} -> {vote.get('target')}" for vote in vote_round.get("votes", [])
                ) or "无人投票"
                count_text = self._format_public_counts(vote_round.get("counts", {}))
                tied_targets = vote_round.get("tied_targets") or []
                if vote_round.get("winner"):
                    result_text = f"{vote_round['winner']} 当选"
                elif tied_targets:
                    result_text = f"平票：{self._join_names(tied_targets)}"
                else:
                    result_text = "无人胜出"
                lines.append(f"- 第 {round_index} 轮票型：{vote_text}；票数：{count_text}；结果：{result_text}")
                lines.append(
                    f"  本轮无投票权上警玩家：{self._join_names(ineligible_voters)}；"
                    f"已投警下玩家：{self._join_names(actual_voters)}；"
                    f"未投警下玩家：{self._join_names(missing_voters)}。"
                    "只有最初未上警玩家参与警长投票；上警候选人不投票，不要指控上警候选人未投票。"
                    "票型中出现的人视为已经投票，不要指控其未投。"
                )

            lines.append(f"- 最终警长：{election.get('winner') or '无'}")

        return "\n".join(lines)

    @staticmethod
    def _format_public_counts(counts: dict | None) -> str:
        if not counts:
            return "无人得票"
        return "、".join(f"{name} {count:g}票" for name, count in counts.items())

    def _format_day_vote_event(self, item: dict) -> list[str]:
        votes = item.get("votes", [])
        vote_text = "、".join(f"{vote.get('voter')} -> {vote.get('target')}" for vote in votes) or "无人投票"
        lines = [f"投票记录：{vote_text}"]

        counts = item.get("counts")
        if counts:
            lines.append(f"票数：{self._format_public_counts(counts)}")

        eligible_voters = [str(name) for name in item.get("eligible_voters", []) if name]
        actual_voters = [str(name) for name in item.get("actual_voters", []) if name]
        if not actual_voters:
            actual_voters = [str(vote.get("voter")) for vote in votes if vote.get("voter")]
        missing_voters = [str(name) for name in item.get("missing_voters", []) if name]
        if eligible_voters or actual_voters or missing_voters:
            lines.append(
                f"应投玩家：{self._join_names(eligible_voters)}；"
                f"已投玩家：{self._join_names(actual_voters)}；"
                f"未投玩家：{self._join_names(missing_voters)}。票型中出现的人视为已经投票，不要指控其未投。"
            )

        tied_targets = item.get("tied_targets") or []
        if tied_targets:
            lines.append(f"平票目标：{self._join_names(tied_targets)}")

        vote_rounds = item.get("vote_rounds") or []
        if vote_rounds:
            for vote_round in vote_rounds:
                round_index = vote_round.get("round", 1)
                round_votes = vote_round.get("votes", [])
                round_vote_text = "、".join(
                    f"{vote.get('voter')} -> {vote.get('target')}" for vote in round_votes
                ) or "无人投票"
                round_count_text = self._format_public_counts(vote_round.get("counts", {}))
                round_ties = vote_round.get("tied_targets") or []
                if vote_round.get("eliminated"):
                    result_text = f"放逐 {vote_round['eliminated']}"
                elif round_ties:
                    result_text = f"平票：{self._join_names(round_ties)}"
                else:
                    result_text = "无人被放逐"
                lines.append(f"第 {round_index} 轮放逐票：{round_vote_text}；票数：{round_count_text}；结果：{result_text}")

        sheriff_tiebreak = item.get("sheriff_tiebreak") or {}
        if sheriff_tiebreak:
            lines.append(f"警长归票：{sheriff_tiebreak.get('sheriff')} -> {sheriff_tiebreak.get('target')}")

        if item.get("idiot_reveal"):
            lines.append(f"白痴翻牌：{item.get('idiot_reveal')} 被投出但免死并失去投票权")

        if "eliminated" in item:
            lines.append(f"放逐结果：{item.get('eliminated') or '无人被放逐'}")
        return lines
    def _current_sheriff_speeches_block(self) -> str:
        phase_labels = {
            "sheriff_campaign": "警上发言",
            "sheriff_runoff": "PK发言",
        }
        lines = []
        for speech in self.game.speeches:
            if speech.round_number != self.game.round_number or speech.phase not in phase_labels:
                continue
            if not speech.public_speech:
                continue
            lines.append(f"- {phase_labels[speech.phase]} {speech.speaker}：{self._trim_public_text(speech.public_speech, 260)}")
        return "\n".join(lines) if lines else "暂无已公开竞选发言。"

    def _live_sheriff_vote_rounds_block(self, vote_rounds: list[dict] | None = None) -> str:
        if not vote_rounds:
            return "暂无已完成警长票型。"

        lines = []
        for vote_round in vote_rounds:
            vote_text = "、".join(
                f"{vote.get('voter')} -> {vote.get('target')}" for vote in vote_round.get("votes", [])
            ) or "无人投票"
            count_text = self._format_public_counts(vote_round.get("counts", {}))
            tied_targets = vote_round.get("tied_targets") or []
            if vote_round.get("winner"):
                result_text = f"{vote_round['winner']} 当选"
            elif tied_targets:
                result_text = f"平票：{self._join_names(tied_targets)}"
            else:
                result_text = "无人胜出"
            lines.append(f"- 第 {vote_round.get('round', 1)} 轮：{vote_text}；票数：{count_text}；结果：{result_text}")
        return "\n".join(lines)

    def _live_sheriff_context_block(self, candidates: list[str], vote_rounds: list[dict] | None = None) -> str:
        return f"""## 当前警长竞选上下文
首夜死讯状态：若这是第 1 天警长竞选，昨夜死亡信息尚未公开；不要说"平安夜"，也不要假装知道谁死亡。
当前可投候选人/PK候选人：{self._join_names(candidates)}
警长投票规则：只有最初未上警玩家可以投票；所有上警候选人都不参与警下投票，即使某个上警玩家没有进入后续 PK 轮，也不能因此指控其"没投票"。

### 已公开竞选发言
{self._current_sheriff_speeches_block()}

### 已完成警长票型
{self._live_sheriff_vote_rounds_block(vote_rounds)}
"""

    def _current_day_vote_runoff_speeches_block(self) -> str:
        lines = []
        for speech in self.game.speeches:
            if speech.round_number != self.game.round_number or speech.phase != "day_vote_runoff":
                continue
            if not speech.public_speech:
                continue
            lines.append(f"- 放逐PK {speech.speaker}：{self._trim_public_text(speech.public_speech, 260)}")
        return "\n".join(lines) if lines else "暂无放逐PK发言。"

    def _live_day_vote_rounds_block(self, vote_rounds: list[dict] | None = None) -> str:
        if not vote_rounds:
            return "暂无已完成放逐票型。"

        lines = []
        for vote_round in vote_rounds:
            vote_text = "、".join(
                f"{vote.get('voter')} -> {vote.get('target')}" for vote in vote_round.get("votes", [])
            ) or "无人投票"
            count_text = self._format_public_counts(vote_round.get("counts", {}))
            tied_targets = vote_round.get("tied_targets") or []
            if vote_round.get("eliminated"):
                result_text = f"放逐 {vote_round['eliminated']}"
            elif tied_targets:
                result_text = f"平票：{self._join_names(tied_targets)}"
            else:
                result_text = "无人被放逐"
            lines.append(f"- 第 {vote_round.get('round', 1)} 轮：{vote_text}；票数：{count_text}；结果：{result_text}")
        return "\n".join(lines)

    def _live_day_vote_context_block(self, candidates: list[str], vote_rounds: list[dict] | None = None) -> str:
        return f"""## 当前放逐投票上下文
当前可投目标：{self._join_names(candidates)}
白天放逐平票规则：警徽仍在场时警长有 {self.game.rules.sheriff_vote_multiplier:g} 票，通常由警徽票权打破平票；只有没有有效警徽时，前两轮平票目标才进入下一轮 PK 发言并继续投票，第三轮后仍平才无人放逐。

### 已公开放逐PK发言
{self._current_day_vote_runoff_speeches_block()}

### 已完成放逐票型
{self._live_day_vote_rounds_block(vote_rounds)}
"""

    def _identity_reasoning_guide(self) -> str:
        if self.player.role in WOLF_ROLES:
            lines = [
                "## 本轮狼队推理任务",
                "请先在 inner_thought 中更新你的牌桌判断和狼队局势，再决定公开发言或投票：",
                "- 已确认信息：公开死亡、投票、警长、你自己的狼队硬信息",
                "- 队友状态：确认哪些队友仍存活、哪些已经出局；不要把名单外玩家当成疑似队友",
                "- 神位判断：谁更像预言家/女巫/猎人/守卫等关键神，依据必须来自公开发言、投票和死亡顺序",
            ]
            lines.extend([
                "- 坑位压力：用本局配置、公开死亡、身份关键词线索和票型制造身份压力；可以要求别人说明自己占哪个民坑/神坑、谁与谁对跳、哪些身份口径互相挤压",
                "- 伪装方案：把神职衣服、民牌口径、倒钩、冲票、对跳等都当作候选方案；面对明确神职起跳时，先比较身份对抗和票型对抗，单纯质疑逻辑只能作为辅助材料；按公开证据和队友状态自行判断，不要默认等队友起跳，也不要默认永远穿民",
                "- 对跳提醒：好人的坑位逻辑是「有人跳了我就不能跳」，你的狼人逻辑必须相反——有人起跳说明这件衣服有信任度，你就更应该对跳。不要因为坑位而自我设限。",
                "- 正逻辑与反逻辑运用：①用**正逻辑**编造发言——代入闭眼好人视角，从公开信息出发推理，推理链要可见（「因为A说了X、B投了Y，所以我觉得...」）。②用**反逻辑**自检——从好人视角反推你的假身份是否合理（「如果我真的是预言家，我会验这个人吗？我的警徽流合理吗？」）。③绝对避免**伪逻辑**——那些听起来有道理但实际缺乏依据的推理（如「我是预言家因为我是第一个起跳的」），容易被好人识破。",
                "- 抗推判断：哪些好人位置更容易被全场接受为放逐目标，哪些位置不能硬推",
                "- 关系链：谁在保谁、踩谁、跟票谁、回避谁，判断可利用的冲突和风险",
                "- 下一步：说明最值得穿衣服、对跳、抗推、倒钩、冲票、刀或自爆的目标，以及为什么它比其他选择更优",
                "- 屠边刀法：本局屠边，狼人只需清空神坑或民坑任意一边。刀人前自问：我刀的对象是神还是民？刀他/她能推进清空哪一边？不要来回切换目标阵营。",
                "- 胜负条件：如果本局是屠边，狼人只需让神坑或民坑任意一边清空即可获胜；请基于公开信息、你的私有信息和身份工作区，自行判断当前是否存在关键神/关键民生死日，但不要把未公开身份当公共事实。",
                "- 笔记更新：如果身份判断有变化，私有便签优先以「身份工作区：」开头输出完整新版身份工作区，写清谁明确报身份、谁只是疑似、谁没交代、谁需要被逼身份；系统会按标签覆盖同类便签",
                "公开发言要伪装成可被好人接受的公共逻辑；不要暴露真实狼队信息，也不要按好人视角排狼坑。",
                "",
                "**发言前睁眼自检**：检查你的 public_speech 是否包含：①对死者惋惜而非分析 ②默认某人是好人 ③提及死亡方式 ④替未发言者开脱 ⑤信息量超过闭眼范围。如有，改写。详见系统提示「睁眼发言避坑指南」。",
            ])
            return "\n".join(lines)

        guide = [
            "## 本轮排位推理任务",
            "请先在 inner_thought 中更新你的牌桌判断，再决定公开发言或投票：",
            "- 已确认信息：公开死亡、投票、警长、你自己的秘密信息",
            "- 身份声明：谁跳了什么身份，是否与投票/死亡/发言顺序矛盾",
            "- 一手消息优先：别人转述「X说了Y」不等于你亲耳听到X说Y。狼人可以通过歪曲、截取、断章取义来误导你。做判断前，先回溯发言记录确认X是否真的说了Y、上下文是什么、语气和时机是否一致。不要不加思索地接受转手消息。",
            "- 找狼三合一法则：**发言+票型+行为**三项结合判断，任何单一维度都不足以定狼。信息溢出（知道不该知道的）+ 抱团冲票（和某些人投票总是一致）+ 划水不盘逻辑（全场不说实质内容）→ 铁狼。",
            "- 正逻辑与反逻辑运用：①用**反逻辑**找狼——代入狼人视角，「如果我是狼，我会怎么打？」某人起跳预言家的时机对他有什么收益？某人站边是否刻意回避了关键矛盾？②用**正逻辑**验证——从闭眼好人视角出发，这个人的发言是否逻辑自洽、是否前后一致、是否基于公开信息逐步推理。③识别**伪逻辑**——留意那些「听起来有道理但经不起推敲」的发言，比如「他是第一个起跳的所以一定是真的」「他敢查杀警下所以有力度」。伪逻辑的共同特征：前提本身需要被证明。",
            "- 听发言的正确姿势：①先以**善意**理解对方想表达什么，而不是以恶意拆解 ②听不懂先搁置，听第二轮再判断 ③代入对方视角去想他的发言是否合理 ④时刻保持辩证，盘双边逻辑，不要先入为主死站边。",
            "- 坑位压力：用本局配置、公开死亡和公开起跳来盘民坑、神坑、狼坑；身份不清的位置可以被要求交代自己占什么坑，或解释为什么暂时不亮身份",
            "- 位置推理：逐个存活位置判断更可能是哪些身份，不要只给出一个武断标签；至少区分「更像神/更像民/更像狼/信息不足」",
            "- 关系链：谁在保谁、踩谁、跟票谁、回避谁——但注意，别人告诉你的关系链可能已经是被加工过的。自己从发言记录中核对。",
            "- 坑位排序：把存活玩家粗分为偏好、待验/待听、狼坑候选，不要只凭单句情绪判断",
            "- 下一步：如果你有技能或票权，说明最值得验、毒、守、归票、刀或放逐的目标，以及为什么它比其他位置更优",
            "- 胜负条件：如果本局是屠边，好人需要避免神坑或民坑任意一边被清空；请基于公开信息、你的秘密信息和身份工作区，自行判断是否已经接近某一边被屠完，但不要把未公开身份当公共事实。",
            "- 笔记更新：如果身份判断有变化，私有便签优先以「身份工作区：」开头输出完整新版身份工作区，写清谁明确报身份、谁只是疑似、谁没交代、谁需要被逼身份；系统会按标签覆盖同类便签",
            "公开发言只能表达你愿意让全场听见的部分；不要把未公开的真实身份当作公共事实。",
            "- **被质疑时先判断再回应**：别人说你的逻辑有错误，不等于你真的错了。狼人杀中很多质疑是狼人在故意搅浑水。先判断对方的质疑是否有实质依据——如果没有，坚持你的判断并指出对方质疑中本身的问题。不要因为被点名就立刻修改自己的结论。"
        ]
        if self.player.role == Role.SEER:
            guide.extend(
                [
                    "",
                    "预言家特别要求：把验人结果放进位置逻辑里，而不是只报结果。",
                    "- 金水不是永远免死：继续观察其站边、投票和是否替狼打掩护",
                    "- 查杀要说明狼同伴可能在哪里：看谁保他、谁切割过早、谁回避评价",
                    "- 如果你还没起跳，评估警徽流、遗言风险和今晚可能被刀的风险",
                    "- 优先给出下一验人方向：从未验存活玩家里找信息量最大的交叉点",
                ]
            )
        return "\n".join(guide)

    def _was_named_in_current_round(self) -> bool:
        return any(
            speech.speaker != self.player.name and self.player.name in (speech.public_speech or "")
            for speech in self._current_round_discussion_speeches()
        )

    def _visible_wolf_count_including_self(self) -> int:
        self_count = 1 if self.player.status.value == "alive" else 0
        return self_count + len(self._alive_visible_wolf_teammates())

    def _public_vote_weight(self, player: Player) -> float:
        if not player.vote_right:
            return 0.0
        if self.game.sheriff_name == player.name:
            return float(self.game.rules.sheriff_vote_multiplier)
        return 1.0

    def _wolf_strength_before_self_destruct_block(self) -> str:
        if self.player.role not in WOLF_ROLES:
            return ""
        known_wolf_names = {self.player.name} if self.player.status.value == "alive" else set()
        known_wolf_names.update(self._alive_visible_wolf_teammates())
        known_wolves = [player for player in self.alive_players if player.name in known_wolf_names]
        non_confirmed = [player for player in self.alive_players if player.name not in known_wolf_names]
        known_vote_power = sum(self._public_vote_weight(player) for player in known_wolves)
        non_confirmed_vote_power = sum(self._public_vote_weight(player) for player in non_confirmed)

        pressure_lines = [
            "## 自爆前狼队实力核算",
            f"- 按你已确认的狼队名单保守计算：已知存活狼人 {len(known_wolves)} 名（{self._join_names([player.name for player in known_wolves])}）；非已确认队友存活位 {len(non_confirmed)} 名（{self._join_names([player.name for player in non_confirmed])}）。",
            f"- 公开票权粗算：已知狼队票权 {known_vote_power:g}，非已确认队友票权上限 {non_confirmed_vote_power:g}（含警徽权重与失票状态）。",
        ]
        if len(known_wolves) >= len(non_confirmed) or known_vote_power >= non_confirmed_vote_power:
            pressure_lines.append("- 你已知狼队人数或票权不劣；自爆会直接减少狼数、放弃票权，并坐实身份，通常先比较冲票、逼身份、穿衣服或转移焦点。")
        elif len(non_confirmed) - len(known_wolves) <= 1 or non_confirmed_vote_power - known_vote_power <= 1:
            pressure_lines.append("- 当前接近人数或票权均势；自爆会让狼队从接近均势变成主动减员，必须先算清下一轮是否还有足够票数和刀数。")
        else:
            pressure_lines.append("- 即使狼队暂时落后，自爆也不是默认补救；先比较继续留场发言、身份对抗、冲票和夜间刀口是否更有收益。")
        if self.game.rules.win_rule == WinRule.PARITY:
            pressure_lines.append("- 本局是人数相等判胜；当狼人数量接近或达到好人数量时，先核对胜负条件和票权，不要用自爆破坏已经接近达成的结构。")
        return "\n".join(pressure_lines)

    def _is_last_visible_wolf_alive(self) -> bool:
        return self.player.role in WOLF_ROLES and self._visible_wolf_count_including_self() == 1

    def _last_wolf_self_destruct_hard_fact(self) -> str:
        if not self._is_last_visible_wolf_alive():
            return ""
        return (
            "LAST_WOLF_NO_NIGHT_KILL. 最后狼人自爆硬事实：你当前是自己已知范围内唯一存活狼人。"
            "如果你白天自爆出局，场上将没有你已知的狼人能在夜晚执行刀人；不要把自爆理解成「切夜后我还能刀」。"
            "As the last actionable wolf, no one can perform a night kill after you self-destruct; do not imagine that you can explode and then kill tonight."
            "普通狼人最后一狼自爆通常等于交出最后狼位并让好人获胜；an ordinary last-wolf self-destruct usually loses unless a special rule creates immediate decisive value. "
            "否则优先考虑活着发言、穿衣服、冲票、抗辩或制造新焦点。"
        )

    def should_offer_day_self_destruct(self) -> bool:
        if self.player.role not in WOLF_ROLES:
            return False
        if self.player.role == Role.WHITE_WOLF and not self.game.rules.white_wolf_explode_during_day:
            return False
        return True

    def _day_self_destruct_context_block(self) -> str:
        facts: list[str] = []
        if self._was_named_in_current_round():
            facts.append("本轮公开讨论里已有其他玩家点名你。")
        if self._visible_wolf_count_including_self() == 1:
            facts.append("你当前是自己已知范围内唯一存活狼人；自爆出局后夜晚将没有你已知的狼人可以刀人，通常会直接输。")
        if self.game.sheriff_name == self.player.name:
            facts.append("你当前持有警徽；自爆会影响警徽流向和白天票权结构。")

        fact_block = "\n".join(f"- {item}" for item in facts) if facts else "- 当前没有特殊的自爆相关局势因素。"
        last_wolf_hard_fact = self._last_wolf_self_destruct_hard_fact()
        return (
            "\n\n## 自爆教育（规则允许，但极少是正确的选择）\n"
            f"{self._visible_wolf_roster_block()}\n"
            f"{fact_block}\n"
            f"{last_wolf_hard_fact}\n"
            f"{self._wolf_strength_before_self_destruct_block()}\n"
            "### 自爆的核心原则：为收益而爆，不为情绪而爆\n"
            "自爆前自问三个问题：①我是警长吗？（不是警长自爆不能吞警徽）②能保队友吗？③能刀对神吗？三者无一，则不爆。\n"
            "\n"
            "### 自爆的真实代价\n"
            "- 自爆确认你是狼——所有跟你站过边、保过你、跟过你票的好人都会获得身份加分。\n"
            "- 自爆不会保护队友——队友仍会被怀疑、被盘问。你自爆只是少了一张狼票，队友压力一点没少。\n"
            "- 自爆跳过放逐投票——如果不自爆，放逐投票可能出到好人。自爆等于主动替好人省了一次可能出错的投票。\n"
            "- 自爆后直接进夜——白天讨论会继续产生信息（发言、站边、票型），自爆阻断了对狼队可能有利的信息流。\n"
            "\n"
            "### 吞警徽的前提（常被误解）\n"
            "**只有警长自爆才能吞警徽。** 如果你不是警长，自爆只是你个人出局，警徽仍然在警长手中，不会消失，不会闷掉。不是警长的悍跳狼自爆不会有吞警徽效果——你只是在白白送死。如果你持有警徽，自爆前要考虑警徽流向。\n"
            "\n"
            "### 什么情况下自爆才可能值得（六种场景）\n"
            "1. **警上接查杀且你是警长/能抢到警徽 → 吞警徽**：你持有警徽（或你自爆后警徽会消失），且真预言家大概率拿不到警徽。自爆吞掉警徽才有收益。**如果你不是警长，自爆不能吞警徽。**\n"
            "2. **队友在警徽流中 → 保队友**：真预言家留的警徽流里有你的狼队友。自爆阻止预言家传递验人信息，保护队友不被查验。\n"
            "3. **聊爆必出局 → 止损**：你已经明显聊爆，继续留场只会暴露更多狼队信息。自爆防止好人从你的发言中盘出狼坑和队友。\n"
            "4. **双爆刀预言家 → 闷警徽**：第一狼自爆→进夜刀预言家→第二天第二狼再自爆→再刀女巫。警徽被闷，预言家双夜无法发言，好人盲推。两狼换两神，大赚。\n"
            "5. **公共狼站边真预言家 → 旋风倒钩**：你聊爆式站边真预言家，让好人误以为你是倒钩好人，适时自爆掩护悍跳狼队友。\n"
            "6. **抿出女巫 → 锁胜局**：你确认女巫身份且其已无药。双爆刀掉女巫和预言家，留下两狼对两神进入生推局，狼在暗处绑票。\n"
            "\n"
            "### 自爆三大禁忌\n"
            "- **不要为了自爆而自爆**：每次自爆必须拿到明确正收益。拿不到好处就活着抗推好人。\n"
            "- **不要在队友已占优时自爆**：如果悍跳狼发言极好、好人纷纷站错边，你自爆反而帮好人止损，断送队友的大好局面。\n"
            "- **不要忽略板子特性**：有守卫的板子单爆后要防平安夜；狼美人骑士板双爆可能负收益；狼王被归票时不要自爆（被放逐再开枪带走关键神）。\n"
            "\n"
            "### 不同狼牌的自爆差异\n"
            "- **普通狼人**：自爆收益最低。没有带人能力，自爆只等于提前出局。除非能打断预言家报验人这种关键信息节点，否则几乎永远不值得。\n"
            "- **白狼王**：自爆带人收益最高。可以直接带走预言家/女巫改变轮次。\n"
            "- **狼王**：被归票时绝对不要自爆。你的核心能力是被放逐后开枪带人——自爆等于主动放弃这个能力，白送一命。被归票时接受放逐是收益最高的选择。只有在确认今晚必吃毒（毒死不能开枪）且无法被守卫保护时，自爆才勉强可考虑。\n"
            "- **狼美人**：骑士可以戳、守卫能守平安夜，板子中双爆收益较低。\n"
            "\n"
            "上面是教育内容，不是系统命令。最终是否自爆由你根据局势自行判断。"
        )

    def _base_system_prompt(self) -> str:
        role_name = ROLE_NAMES_ZH[self.player.role]
        role_desc = ROLE_DESCRIPTIONS[self.player.role]
        personality = self.player.personality or "冷静理性，善于观察和分析。"
        strategies = "\n".join(f"- {item}" for item in self.memory.strategies) if self.memory.strategies else "暂无"

        return f"""你是 {self.player.name}，一名正在进行狼人杀对局的 AI 玩家。
## 你的性格
{personality}

## 你的身份
你是【{role_name}】。{role_desc}

## 本局配置
总玩家数：{len(self.game.players)}
角色配置：{self._role_config_line()}
房规摘要：{summarize_rules(self.game.rules)}

## 座位表（游戏开始时就已确定，全程不变）
{"\n".join(f"{i}. {p.name}" for i, p in enumerate(self.game.players, start=1))}

座位是固定的公共信息。发言顺序按顺时针轮转（详见下方规则）。推理时请使用座位号——说「3号发言有问题」比说「某某发言有问题」更清晰，也更像真实玩家的思维方式。

{WEREWOLF_RULES}

{WEREWOLF_GLOSSARY}

## 本局房规说明
{build_rules_summary(self.game)}

## 你的历史经验
{strategies}

## 输出格式
你必须严格输出 JSON，不要附带任何额外说明：
{{
  "inner_thought": "你的真实思考，其他玩家看不到",
  "public_speech": "你要公开说的话。夜间没有公开发言时必须为空字符串",
  "private_note": "默认应填写，并尽量以固定标签开头：身份工作区：/战术计划：/假身份：/狼队计划：/技能计划：。同标签便签会被系统覆盖更新；请输出完整新版内容，不要只写局部新增。即使暂无新变化，也要简短写下你仍坚持的核心判断或下一步计划",
  "delete_notes": [固定填 []。不要用删除编号来修正便签；需要修正时请用同标签 private_note 输出完整新版内容],
  "action": <action_schema 或 null>
}}"""

    def _memory_augmented_system_prompt(self) -> str:
        return self._base_system_prompt() + f"""

## Long-term memory record
{self._memory_record_block()}

## Same-role summary
{self._role_memory_summary_block()}

## Retrieved similar historical games
{self._retrieved_memories_block()}

## Memory usage guidance
- Treat retrieved memories as priors, not hard facts.
- Give highest weight to same-role and similar-board memories.
- If current table evidence conflicts with old memory, trust current evidence.
- Use history to improve reads, pacing, fake claims, vote timing, and target selection.
- 关键决策前先检查局内便签；如果当前证据推翻了既有判断，先在 inner_thought 说明为什么改判，再用同标签 private_note 输出完整新版便签，由系统覆盖更新。
- 请把身份判断主要维护在你自己的"身份工作区："便签里，而不是依赖系统关键词摘录。身份工作区应由你自己写出：每个焦点位可能身份、明确/疑似/未交代身份边界、谁需要被逼身份、当前民坑/神坑/狼坑是否拥挤。
- 当新增发言、投票、死亡或私有事实改变身份判断时，优先用 private_note 以"身份工作区："开头输出完整新版身份工作区；系统会覆盖同标签旧内容，不要另写一条局部新增。
- 狼人若发现既有便签和最新狼队夜话冲突，优先以最新狼队夜话、确认队友名单和当前公开事实为准；用「假身份：」或「狼队计划：」输出完整新版分工，再行动。
- 当你形成新的关键结论时，优先把这些内容写进 private_note：已确认队友存亡、明确跳身份、今晚优先刀口、明天票型计划、需要复核的矛盾。
- 除非当前回合确实没有任何可复用信息，否则默认产出 private_note；如果暂时没有新变化，就简短重申你仍坚持的身份判断或下一步计划。
- 每次回复都默认通过同标签 private_note 更新便签；delete_notes 固定写 []。不要用删除编号来修正便签，系统会按标签覆盖更新。

## 局内私有便签
{self._in_game_notes_block()}
这些便签只属于你自己，用来保持本局战术和身份口径连续；但它们不能覆盖引擎提供的私有技能事实。若既有便签与后续狼队夜话或公开事实冲突，请用相同标签输出完整新版便签，让系统覆盖旧内容，而不是同时保留两套计划。

{self._wolf_chat_history_block()}
{self._private_skill_truth_block()}
{self._wolf_strategy_reference_block()}
{self._wolf_advanced_tactics_block()}
{self._closed_eye_guide_block()}
{self._wolf_killing_guide_block()}
{self._wolf_self_knife_guide_block()}
{self._seer_guide_block()}
{self._public_role_claims_block()}
{self._wolf_targeting_priority_block()}
{self._wolf_deception_strategy_block()}
{self._wolf_sheriff_claim_strategy_block()}
{self._wolf_active_pressure_check_block()}
{self._wolf_god_disguise_playbook_block()}
"""

    def build_night_system_prompt(self) -> str:
        return (
            self._memory_augmented_system_prompt()
            + "\n\n现在是夜晚。你只能进行内部思考，不能公开发言，因此 public_speech 必须为空字符串。"
            + self._role_night_instruction()
        )

    def build_discuss_system_prompt(self) -> str:
        return self._memory_augmented_system_prompt() + self._role_day_info()

    def build_sheriff_nomination_system_prompt(self) -> str:
        return self._memory_augmented_system_prompt() + self._role_day_info()

    def build_vote_system_prompt(self) -> str:
        return self._memory_augmented_system_prompt() + self._role_day_info()

    def _sheriff_info(self) -> str:
        if self.game.sheriff_name != self.player.name:
            return ""
        multiplier = self.game.rules.sheriff_vote_multiplier
        return f"\n你当前持有警徽。你的投票权重为 {multiplier:g}，平票时需要由你归票；若你出局，可以移交或撕毁警徽。"

    def _in_game_notes_block(self) -> str:
        notes = self.game.agent_notes.get(self.player.name, [])
        if not notes:
            return "暂无。你可以在 private_note 中保存本局后续要坚持或复核的战术要点。"
        visible_notes = notes[-8:]
        lines = []
        for index, note in enumerate(visible_notes, start=1):
            body = note.split(": ", 1)[-1] if ": " in note else note
            marker = " [硬事实不可删]" if body.startswith(("狼队硬信息：", "身份素材：")) else ""
            lines.append(f"{index}. {self._trim_public_text(note, 220)}{marker}")
        return "\n".join(lines)

    def _own_skill_records(self) -> list[str]:
        phase_labels = {
            "night_werewolf": "狼人夜刀",
            "night_wolf_beauty": "狼美人魅惑",
            "night_stone_gargoyle": "石像鬼查验",
            "night_seer": "预言家查验",
            "night_witch": "女巫用药",
            "night_guard": "守卫守护",
            "night_silencer": "禁言",
            "night_gravekeeper": "守墓",
            "hunter_revenge": "猎人开枪",
            "wolf_king_revenge": "狼王开枪",
            "sheriff_transfer": "警徽流转",
        }
        records = []
        for speech in self.game.speeches:
            if speech.speaker != self.player.name or speech.phase not in phase_labels or not speech.skill_info:
                continue
            records.append(
                f"第 {speech.round_number} 轮 {phase_labels[speech.phase]}：{self._trim_public_text(speech.skill_info, 260)}"
            )
        return records[-6:]

    def _private_skill_truth_block(self) -> str:
        role = self.player.role
        facts: list[str] = []

        if role in WOLF_ROLES:
            facts.append(self._visible_wolf_roster_block())

        if role == Role.SEER:
            checks = []
            checked_targets = set()
            for item in self.game.history:
                if item.get("type") == "seer_check" and item.get("player") == self.player.name:
                    result = "狼人" if item["is_wolf"] else "好人"
                    checks.append(f"第 {item['round']} 夜查验 {item['target']}：{result}")
                    checked_targets.add(item["target"])
            unchecked_alive = [
                player.name
                for player in self.alive_other_players
                if player.name not in checked_targets
            ]
            facts.append("预言家验人结果：\n" + (chr(10).join(checks) if checks else "暂无"))
            facts.append(f"未验存活玩家：{self._join_names(unchecked_alive)}")

        if role == Role.WITCH:
            facts.append(f"解药：{'未使用' if self.game.witch_has_save else '已用完'}；毒药：{'未使用' if self.game.witch_has_poison else '已用完'}")
            if self.game.witch_has_save:
                kill_target = self.game.night_actions.werewolf_target if self.game.night_actions else None
                facts.append(f"当前你可见的狼刀目标：{kill_target or '无'}")
            else:
                facts.append("解药已用完：从此夜开始你不再获得当夜狼刀目标信息。")

        if role == Role.GUARD:
            last_guard = self.game.night_actions.last_guard_target if self.game.night_actions else None
            current_guard = self.game.night_actions.guard_target if self.game.night_actions else None
            facts.append(f"上一晚守护目标：{last_guard or '无'}；本晚已登记守护：{current_guard or '未登记'}")

        if role == Role.GRAVEKEEPER:
            result = self.game.night_actions.gravekeeper_alignment if self.game.night_actions else None
            facts.append(f"守墓结果：{result or '暂无'}")

        if role == Role.STONE_GARGOYLE:
            target = self.game.night_actions.stone_gargoyle_target if self.game.night_actions else None
            result = self.game.night_actions.stone_gargoyle_result if self.game.night_actions else None
            result_text = ROLE_NAMES_ZH[result] if result else "暂无"
            facts.append(f"石像鬼查验：{target or '暂无'} -> {result_text}")

        if role == Role.WOLF_BEAUTY:
            last_target = self.game.night_actions.last_wolf_beauty_target if self.game.night_actions else self.game.current_charmed_target
            current_target = self.game.night_actions.wolf_beauty_target if self.game.night_actions else self.game.current_charmed_target
            facts.append(f"狼美人魅惑：上一目标 {last_target or '无'}；当前目标 {current_target or '无'}")

        if role == Role.SILENCER:
            last_target = self.game.night_actions.last_silencer_target if self.game.night_actions else self.game.silenced_player
            current_target = self.game.night_actions.silencer_target if self.game.night_actions else self.game.silenced_player
            facts.append(f"禁言记录：上一目标 {last_target or '无'}；当前目标 {current_target or '无'}")

        skill_records = self._own_skill_records()
        if skill_records:
            facts.append("你的技能行动记录：\n" + "\n".join(skill_records))

        if not facts:
            return ""

        return (
            "\n\n## 最高优先级私有技能事实\n"
            "这些是引擎根据你的身份和技能提供的硬事实，优先级高于公开发言、投票舆论、长期记忆、局内便签、他人评价和你自己的诈身份话术。\n"
            "你可以在公开发言里隐藏、延迟或设计性表达技能信息来骗别人；但 inner_thought 和真实推理必须始终以这里为准，不能被自己的话术骗回去。\n"
            + "\n".join(f"- {fact}" for fact in facts)
        )

    def _role_day_info(self) -> str:
        role = self.player.role
        if role in WOLF_ROLES:
            lines = [f"\n\n## 你的秘密信息\n你属于狼人阵营。你的目标不是自己活下去，而是**狼队屠边获胜**。\n{self._visible_wolf_roster_block()}"]

            if role == Role.WHITE_WOLF and self.game.rules.white_wolf_explode_during_day:
                lines.append("白狼王规则上可以在白天自爆带人；是否发动由你判断，但应优先寻找高收益目标和明确战术理由。")
                lines.append(self._day_self_destruct_context_block())
            elif role == Role.WOLF_KING:
                lines.append(
                    "\n## 你的狼王身份与技能\n"
                    "你被投票放逐时可以开枪带走一名玩家。夜晚被刀、被决斗等非中毒死亡也能开枪。\n"
                    "**中毒死亡和自爆不能开枪**——这两条是你技能的硬边界。\n"
                    "策略要点：\n"
                    "- 被归票时**不要自爆**：坦然接受放逐，出局后开枪带走关键神（预言家/女巫优先）。被放逐是你的核心收益路径。\n"
                    "- 自爆等于浪费你的带人能力——除非你确认今晚必吃毒且无法被守卫保护。\n"
                    "- 白狼王靠自爆带人，你靠被放逐带人——不要搞混。\n"
                    "- 对跳猎人时注意：你的出局能力和猎人一致，都是被放逐/被刀后开枪。"
                )
                lines.append(self._day_self_destruct_context_block())
            elif role != Role.WHITE_WOLF:
                lines.append("规则允许狼人白天自爆；是否发动由你判断，但这通常是高代价战术，不是常规发言选项。")
                lines.append(self._day_self_destruct_context_block())

            lines.append("\n## 对跳原则：不要用好人思维限制自己")
            lines.append("**好人的坑位逻辑**：「预言家只有一个，有人跳了我就不能跳」——这是好人排除假身份的工具。")
            lines.append("**你的狼人逻辑必须相反**：有人起跳神职，说明这件衣服有好人信任度，你就更应该对跳。同样的神职出现两人起跳 → 好人分不清真假 → 狼人获利。")
            lines.append("因此：")
            lines.append("- 非队友起跳预言家 → 优先考虑自己对跳预言家（而非退让穿民）")
            lines.append("- 非队友起跳女巫 → 优先考虑自己对跳女巫（报银水），尤其在你掌握死亡信息时")
            lines.append("- 非队友起跳猎人 → 狼王优先考虑对跳猎人（狼王技能和猎人相同：被放逐/被刀后开枪带人）；白狼王也可对跳（用自爆带人模拟猎人效果）")
            lines.append("- 非队友起跳守卫 → 守卫无法自证，是任何狼人的安全对跳选择")
            lines.append("- **不要因为「坑位满了」而不跳——让坑位「超载」才是狼人的目标。**")

            lines.append("\n公开发言时优先考虑可持续的伪装、悍跳/对跳、抗辩、倒钩、冲票或转移焦点；面对真神或强身份时，单纯质疑逻辑通常不如制造身份压力。除非收益明显高于继续留场，否则不要用自爆代替发言。")

            sheriff_info = self._sheriff_info()
            if sheriff_info:
                lines.append(sheriff_info)
            return "".join(lines)

        if role == Role.SEER:
            return (
                self._private_skill_truth_block()
                + "\n"
                "请把查验结果与公开发言、投票、死亡和座位关系一起排坑；你的目标是形成可解释的狼坑与好人坑，而不是只复述验人。"
                f"{self._sheriff_info()}"
            )

        if role == Role.WITCH:
            save_status = "未使用" if self.game.witch_has_save else "已用完"
            poison_status = "未使用" if self.game.witch_has_poison else "已用完"
            return f"\n\n## 你的秘密信息\n解药：{save_status}；毒药：{poison_status}。{self._sheriff_info()}"

        if role == Role.GUARD:
            last_guard = self.game.night_actions.last_guard_target if self.game.night_actions else None
            return f"\n\n## 你的秘密信息\n上一晚守护目标：{last_guard or '无'}。{self._sheriff_info()}"

        if role == Role.GRAVEKEEPER:
            last_result = self.game.night_actions.gravekeeper_alignment if self.game.night_actions else None
            if last_result:
                return f"\n\n## 你的秘密信息\n你最近一次得知的放逐结果：{last_result}。{self._sheriff_info()}"
            return f"\n\n## 你的秘密信息\n今晚若昨天地面有放逐者，你会得知其是否属于狼人阵营。{self._sheriff_info()}"

        if role == Role.IDIOT:
            vote_status = "仍有投票权" if self.player.vote_right else "已失去投票权"
            return f"\n\n## 你的秘密信息\n你是白痴，目前{vote_status}。{self._sheriff_info()}"

        if role == Role.KNIGHT:
            return f"\n\n## 你的秘密信息\n你是骑士。白天你可以主动决斗一名玩家。{self._sheriff_info()}"

        return f"\n\n## 你的秘密信息{self._sheriff_info()}" if self._sheriff_info() else ""

    def _role_night_instruction(self) -> str:
        role = self.player.role

        if role in VISIBLE_PACK_WOLF_ROLES:
            return f"""

## 狼人夜间信息
{self._visible_wolf_roster_block()}
请选择今夜要击杀的目标。

**明天的公开身份规划**：
在 private_note 中规划明天的公开身份口径，可以帮助你天亮后快速决策：谁上警、穿什么衣服、准备什么假信息、如何应对真预言家起跳。

action 格式：{{"kill_target": "玩家名"}}"""

        if role == Role.HIDDEN_WOLF:
            if self._is_awakened_hidden_wolf():
                return """

## 隐狼夜间信息
你已觉醒，今夜可以像普通狼人一样选择击杀目标。action 格式：{"kill_target": "玩家名"}"""
            return """

## 隐狼夜间信息
你尚未觉醒，今夜没有主动技能。action 设为 null。"""

        if role == Role.STONE_GARGOYLE:
            if self._is_awakened_stone_gargoyle():
                return """

## 石像鬼夜间信息
你已成为独狼，今夜可以选择击杀目标。action 格式：{"kill_target": "玩家名"}"""
            return """

## 石像鬼夜间信息
今夜你可以查验一名玩家的准确身份。action 格式：{"check_target": "玩家名"}"""

        if role == Role.WOLF_BEAUTY:
            return """

## 狼美人夜间信息
除参与狼人阵营夜间刀口讨论外，你还可以魅惑一名玩家。
action 格式：{"kill_target": "玩家名", "check_target": "要魅惑的玩家名"}"""

        if role == Role.SEER:
            return f"""

## 预言家夜间信息
{self._private_skill_truth_block()}
今夜你可以查验一名玩家的阵营。action 格式：{{"check_target": "玩家名"}}"""

        if role == Role.WITCH:
            lines = [
                "",
                "## 女巫夜间信息",
                f"解药：{'未使用' if self.game.witch_has_save else '已用完'}",
                f"毒药：{'未使用' if self.game.witch_has_poison else '已用完'}",
            ]
            if self.game.witch_has_save:
                kill_target = self.game.night_actions.werewolf_target if self.game.night_actions else None
                lines.append(f"今夜狼刀目标：{kill_target or '无'}")
                if self.game.witch_has_poison:
                    lines.append('action 格式：{"use_save": true/false, "poison_target": "玩家名或 null"}')
                else:
                    lines.append('action 格式：{"use_save": true/false}')
            elif self.game.witch_has_poison:
                lines.append('action 格式：{"poison_target": "玩家名或 null"}')
            else:
                lines.append("action 设为 null。")
            return "\n".join(lines)

        if role == Role.GUARD:
            last_guard = self.game.night_actions.last_guard_target if self.game.night_actions else None
            return f"""

## 守卫夜间信息
上一晚守护目标：{last_guard or '无'}。不能连续两晚守同一人。action 格式：{{"protect_target": "玩家名"}}"""

        if role == Role.SILENCER:
            last_target = self.game.night_actions.last_silencer_target if self.game.night_actions else None
            return f"""

## 禁言长老夜间信息
上一晚禁言目标：{last_target or '无'}。通常不能连续禁言同一人。action 格式：{{"check_target": "玩家名"}}"""

        if role == Role.GRAVEKEEPER:
            return """

## 守墓人夜间信息
如果昨天地面有被放逐玩家，你会自动得知其是否属于狼人阵营。action 设为 null。"""

        return """

## 夜间信息
你在夜晚没有主动技能。action 设为 null。"""

    def _build_history(self) -> str:
        if self.game.round_number <= 1:
            return ""

        sections: list[str] = []
        for round_number in range(1, self.game.round_number):
            lines = [f"## 第 {round_number} 轮回顾"]

            night_deaths = [
                item
                for item in self.game.history
                if item.get("type") == "death" and item.get("round") == round_number and item.get("phase") == "night"
            ]
            if night_deaths:
                lines.append("夜晚死亡：" + "、".join(f"{item['player']}({item['role']})" for item in night_deaths))
            else:
                lines.append("夜晚结果：平安夜")

            speech_lines = self._round_public_speeches(round_number)
            if speech_lines:
                lines.append("公开发言：")
                lines.extend(speech_lines)

            vote_events = [
                item for item in self.game.history if item.get("type") == "day_vote" and item.get("round") == round_number
            ]
            if vote_events:
                for vote_event in vote_events:
                    lines.extend(self._format_day_vote_event(vote_event))

            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    def _night_public_context_block(self) -> str:
        sections = [
            "## 夜晚可用公开信息",
            self._public_board_state(),
            self._public_role_slot_pressure_block(),
            self._public_role_claims_block(),
            (
                "身份起跳只能依据公开发言原文判断：只有玩家明确说「我是预言家/女巫/猎人」等，才算起跳该身份。"
                "不要把支持某个预言家、质疑某个玩家、解释夜晚结果，脑补成「跳女巫」或其他身份。"
            ),
        ]

        history = self._build_history()
        if history:
            sections.append(history)

        sheriff_info = self._public_sheriff_election_block()
        if sheriff_info:
            sections.append(sheriff_info)

        return "\n\n".join(section for section in sections if section)

    def build_night_user_prompt(self) -> str:
        private_context = self._private_skill_truth_block()
        return f"""第 {self.game.round_number} 夜。除你之外的存活玩家：{self._join_names([player.name for player in self.alive_other_players])}

{private_context}

{self._night_public_context_block()}

请执行你的夜间行动。"""

    def build_wolf_private_chat_system_prompt(self) -> str:
        return (
            self._memory_augmented_system_prompt()
            + "\n\nYou are now writing to the wolf-team private chat, not to the public table. "
            "For this special step only, put the teammate-visible private message in public_speech; "
            "it will be stored as wolf-only chat and will not be broadcast as public speech. "
            "Keep action null."
        )

    def build_wolf_private_chat_user_prompt(self, kill_target: str | None) -> str:
        # Compute wolf's position in the chat order
        all_wolves = [p for p in self.game.players if p.status.value == "alive" and p.role in WOLF_ROLES and (p.role in VISIBLE_PACK_WOLF_ROLES or (p.role == Role.HIDDEN_WOLF and self._is_awakened_hidden_wolf()) or (p.role == Role.STONE_GARGOYLE and self._is_awakened_stone_gargoyle()))]
        total = len(all_wolves)
        my_index = next((i for i, w in enumerate(all_wolves) if w.name == self.player.name), -1)
        position = my_index + 1
        is_last = position == total

        position_hint = ""
        if total <= 1:
            position_hint = "你是唯一的狼人，你需要自己制定完整计划。"
        elif is_last:
            position_hint = f"你是 {total} 只狼中最后发言的（第 {position} 位）。前面所有队友的发言你都已经看到了。你的责任不是再给一个建议——而是综合所有人的信息，给出**最终的、完整的、可执行的狼队计划**。指定谁悍跳、穿什么衣服、报什么假信息、谁冲锋谁倒钩。你的发言是本次夜间对话的最终结论。"
        elif position == 1:
            position_hint = f"你是 {total} 只狼中第一个发言的。你的任务是打开局面——给出初始方案：建议谁悍跳、穿什么衣服、报什么假信息。后续队友会基于你的方案补充和修正。不要等队友先开口。"
        else:
            remaining = total - position
            position_hint = f"你是 {total} 只狼中第 {position} 位发言的，你之后还有 {remaining} 位队友。你已经看到前面队友的发言，可以补充、修正或推翻他们的方案。如果你不同意前面的方案，现在就说——等你后面的人发言时可能就来不及了。"

        return f"""## wolf_team_private_chat_turn
今夜击杀目标：{kill_target or 'none'}。

**每只狼只有一次发言机会，本轮对话没有第二轮。** 你说的话就是你对队友的全部协调——如果不说清楚，天亮后各打各的。

{position_hint}

### 你需要协调的内容
- 明天谁上警？如果悍跳预言家，报什么验人（对象+金水/查杀+理由）+ 警徽流（至少2人）？
- 非悍跳位如何站边：谁冲锋（公开支持悍跳狼）、谁倒钩（站真预言家）、谁深水？
- 如果真预言家先起跳并报出矛盾验人，如何应对？
- 是否考虑穿女巫/猎人/守卫等其他神职衣服？银水/枪口威慑/守人逻辑如何准备？
- 指定具体的人和具体的行动，不要用「某人」「看情况」代替人名和计划。

Output requirements:
- public_speech: the private wolf-team message, visible only to wolves with channel access
- private_note: update your own reusable plan. If changing a fake-identity plan, start with "假身份：" or "狼队计划：" and write the complete new version.
- action: null"""

    def build_werewolf_discuss_user_prompt(self, proposals: list[dict], round_num: int) -> str:
        proposal_lines = []
        for proposal in proposals:
            if proposal["name"] == self.player.name:
                proposal_lines.append(f"你上一轮提议刀 {proposal['target']}")
            else:
                proposal_lines.append(f"队友 {proposal['name']} 提议刀 {proposal['target']}")
        private_context = self._private_skill_truth_block()
        max_rounds_hint = "这是最后一轮讨论，必须统一刀口。" if round_num >= 3 else f"最多还有 {3 - round_num} 轮讨论，尽早统一刀口以节省时间。"
        return f"""第 {self.game.round_number} 夜，狼人讨论第 {round_num} 轮。{max_rounds_hint}
上一轮提议：
{chr(10).join(proposal_lines) if proposal_lines else '暂无'}

{private_context}

{self._night_public_context_block()}

请再次给出今夜击杀目标。"""

    def build_discuss_user_prompt(self) -> str:
        speeches_this_round = self._current_round_discussion_speeches()
        previous_speeches = "\n".join(
            f"{speech.speaker}：{speech.public_speech}" for speech in speeches_this_round if speech.speaker != self.player.name
        ) or "你是本轮第一个发言的人。"
        private_context = self._private_skill_truth_block()

        special_hint = "action 设为 null。"
        if self.player.role == Role.WHITE_WOLF and self.game.rules.white_wolf_explode_during_day:
            special_hint = (
                '如果你自主判断白天自爆带人收益足够高，可把 action 设为 {"shoot_target": "玩家名"}；'
                "否则 action 设为 null。你可以自己权衡：当前是否需要打断关键推理、是否已被严重怀疑、带人能否创造明确狼队收益，以及继续穿衣服/对跳是否更赚。"
            )
        elif self.player.role in WOLF_ROLES:
            special_hint = "action 设为 null。优先考虑穿衣服、悍跳/对跳、抗辩、倒钩、冲票和转移焦点。自爆是极端手段，只在基本暴露且继续留场明显更亏时才考虑，不是常规选项。"
        elif self.player.role == Role.KNIGHT:
            special_hint = '如果你决定发动骑士决斗，可把 action 设为 {"shoot_target": "玩家名"}；否则 action 设为 null。'

        extra_context = ""
        if self.player.role in WOLF_ROLES and self.should_offer_day_self_destruct():
            extra_context = f"\n\n{self._day_self_destruct_context_block()}"

        return f"""## 当前游戏信息
第 {self.game.round_number} 天。存活玩家：{self._join_names([player.name for player in self.alive_players])}

{private_context}

{self._public_board_state()}

{self._public_role_slot_pressure_block()}

## 昨夜结果
{self.game.gm_announcement or '游戏刚开始，还没有昨夜信息。'}

{self._build_history()}

{self._public_sheriff_election_block()}
{self._public_role_claims_block()}

## 当前讨论
{previous_speeches}
{extra_context}

{self._identity_reasoning_guide()}

## 你的回合
请结合发言、投票和死亡信息表达你的判断。若身份判断发生变化，请在私有便签中用「身份工作区：」更新你自己的身份分析，而不是照抄系统关键词线索。{special_hint}"""

    def build_last_words_user_prompt(self) -> str:
        prior_last_words = "\n".join(
            f"{speech.speaker}：{speech.public_speech}"
            for speech in self.game.speeches
            if speech.round_number == self.game.round_number and speech.phase == "last_words" and speech.public_speech
        ) or "暂无。"
        sheriff_context = self._public_sheriff_election_block() or "本局当前没有已完成的警长竞选公开信息。"
        private_context = self._private_skill_truth_block()
        current_vote_lines: list[str] = []
        for item in self.game.history:
            if item.get("type") == "day_vote" and item.get("round") == self.game.round_number:
                current_vote_lines.extend(self._format_day_vote_event(item))
        current_vote_context = "\n".join(current_vote_lines) if current_vote_lines else "当前遗言前尚无本轮放逐票型记录。"
        wolf_last_words_hint = ""
        if self.player.role in WOLF_ROLES:
            wolf_last_words_hint = (
                "\n如果你是被投票放逐的狼人，遗言仍然是公开对抗的一部分：你可以继续维持好人身份、"
                "延续悍跳/对跳/查杀口径、误导站边或保护后续刀口。被票出不等于必须提前自爆；"
                "悍跳加查杀即使最终被放逐，遗言也可能继续影响好人视角。"
            )

        return f"""## 遗言上下文
你已经死亡，现在只能发表遗言，action 设为 null。
当前是第 {self.game.round_number} 天。你的身份是 {ROLE_NAMES_ZH[self.player.role]}。

{private_context}

{self._public_board_state()}

{self._public_role_slot_pressure_block()}

## 昨夜结果
{self.game.gm_announcement or '昨夜死讯尚未公布。'}

{self._build_history()}

{sheriff_context}

## 本轮放逐票型
{current_vote_context}

## 本轮已发表遗言
{prior_last_words}

## 遗言要求
请基于你死亡前已经公开的信息发言。若上方出现警长竞选公开信息，说明你已经听过警上发言和警长票型；不要说「这局没听到任何发言」或「没有上警信息」。
你可以简短点评警上发言、警长结果、昨夜死亡、放逐票型，以及你自己的站边或怀疑对象。
你可以再次表明真实身份，或延续你愿意公开坚持的身份口径；遗言会作为公开发言进入后续玩家上下文。{wolf_last_words_hint}"""

    def build_day_vote_runoff_speech_user_prompt(self, candidates: list[str], vote_round: int, vote_rounds: list[dict]) -> str:
        private_context = self._private_skill_truth_block()
        return f"""白天放逐投票第 {vote_round - 1} 轮出现平票，你仍在 PK 目标中。当前 PK 目标：{self._join_names(candidates)}

{private_context}

{self._public_board_state()}

{self._public_role_slot_pressure_block()}

{self._build_history()}

{self._public_sheriff_election_block()}
{self._public_role_claims_block()}

{self._live_day_vote_context_block(candidates, vote_rounds)}

{self._identity_reasoning_guide()}

请发表一段放逐 PK 发言：回应上一轮票型和别人对你的质疑，说明为什么今天不该出你、以及你认为更应该出的目标是谁。action 设为 null。"""

    def build_vote_user_prompt(
        self,
        candidates: list[str] | None = None,
        vote_round: int = 1,
        vote_rounds: list[dict] | None = None,
    ) -> str:
        speech_text = "\n".join(
            f"{speech.speaker}：{speech.public_speech}"
            for speech in self.game.speeches
            if speech.round_number == self.game.round_number and speech.phase in ("discuss", "last_words", "day_vote_runoff", "sheriff_guipiao")
        ) or "暂无发言记录。"
        private_context = self._private_skill_truth_block()
        vote_candidates = candidates or [player.name for player in self.alive_other_players]
        vote_context = self._live_day_vote_context_block(vote_candidates, vote_rounds) if candidates else ""
        vote_scope = (
            f"本轮是第 {vote_round} 轮放逐投票，请只在当前 PK/可投目标中选择：{self._join_names(vote_candidates)}。"
            if candidates
            else "请投票给你认为最像狼的玩家。"
        )

        return f"""## 第 {self.game.round_number} 天投票
除你之外的存活玩家：{self._join_names([player.name for player in self.alive_other_players])}

{private_context}

{self._public_board_state()}

{self._public_role_slot_pressure_block()}

## 今日发言
{speech_text}

{self._build_history()}

{self._public_sheriff_election_block()}
{self._public_role_claims_block()}
{vote_context}

{self._identity_reasoning_guide()}

不要长篇复述所有发言；inner_thought 用 2-4 句给出票型判断和目标即可。若投票依据改变了身份判断，请用"身份工作区："更新私有便签。
{vote_scope} 如果今天不该出票，也可以投给 "abstain"。action 格式：{{"vote_target": "玩家名或 abstain"}}"""

    def build_public_speech_digest_user_prompt(self, speaker_name: str, public_speech: str, phase: str) -> str:
        phase_labels = {
            "sheriff_campaign": "警上发言",
            "sheriff_runoff": "警长PK发言",
            "day_vote_runoff": "放逐PK发言",
            "discuss": "白天发言",
            "last_words": "遗言",
        }
        phase_label = phase_labels.get(phase, phase)

        return f"""你现在不需要公开发言，也不需要立刻投票；只需要私下消化一条新的公开信息，并更新自己的局内便签。

## 新增的公开发言
{speaker_name} 的{phase_label}：
{self._trim_public_text(public_speech, 420)}

{self._public_board_state()}

{self._public_role_slot_pressure_block()}

{self._build_history()}

{self._public_sheriff_election_block()}
{self._public_role_claims_block()}

{self._identity_reasoning_guide()}

任务要求：
- 先自己推理这条新增发言会如何改变你对各个存活位置的身份判断。
- 不要只下单点结论；优先比较 2-4 个最关键位置的变化。
- 不要让系统关键词摘录替你判断"谁报了身份"；请根据原文自己判断这名发言者是明确报身份、疑似暗示、拒绝交代，还是仍需被逼身份。
- 如果你是狼人，请同时更新公开打法判断：继续穿衣服、悍跳/对跳、倒钩、冲票、转移焦点、今晚刀口都只是候选项；不要预设必须刀谁，也不要把被怀疑自动等同于自爆。
- 如果你是狼人且你被推上焦点位，请把神职衣服也纳入候选，但是否穿、穿哪件、何时穿，都由你按当前证据自行判断。
- 如果这条发言没有改变核心判断，也可以明确写"暂无核心改动"，但请说明你仍在坚持什么判断。

输出要求：
- public_speech 必须为空字符串
- action 设为 null
- inner_thought 用 2-4 句写这条发言改变了什么
- 私有便签必须用 1-2 句留下可复用的短便签；如果身份判断变化，优先以「身份工作区：」开头输出完整新版身份工作区，记录各焦点位可能身份、身份边界、待逼身份位和当前坑位压力；系统会覆盖同标签旧内容。如果暂无新变化，也要简短写下你仍坚持的核心判断。"""

    def build_day_self_destruct_reaction_user_prompt(self, latest_speaker: str, latest_speech: str) -> str:
        if self.player.role == Role.WHITE_WOLF and self.game.rules.white_wolf_explode_during_day:
            action_hint = (
                '只有你判断现在白狼王自爆带人收益明显高于继续穿衣服/对跳/抗辩时，action 才设为 {"shoot_target": "玩家名"}；'
                "否则 action 设为 null。public_speech 必须为空字符串。"
            )
        elif self.player.role == Role.WOLF_KING:
            action_hint = (
                '狼王自爆不能开枪——被放逐才能开枪带人。除非你确认今晚必吃毒且无法被守卫保护，否则永远不要自爆。'
                'action 设为 null。public_speech 必须为空字符串。'
            )
        else:
            action_hint = (
                '只有你判断现在必须立刻自爆打断白天，且继续穿衣服/对跳/抗辩/倒钩都会更亏时，action 才设为 {"self_destruct": true}；'
                "否则 action 设为 null。public_speech 必须为空字符串。如果你是最后一名可行动狼人，自爆后没有狼人能夜刀，通常不是「切夜收益」。"
            )

        return f"""## 发言后即时自爆窗口
刚刚发言者：{latest_speaker}
刚刚发言内容：{self._trim_public_text(latest_speech, 420)}

{self._public_board_state()}

{self._public_role_slot_pressure_block()}

{self._build_history()}

{self._public_sheriff_election_block()}

## 当前讨论记录
{chr(10).join(f"{speech.speaker}：{speech.public_speech}" for speech in self._current_round_discussion_speeches() if speech.public_speech) or '暂无'}

{self._day_self_destruct_context_block()}

        请只判断是否要现在立刻自爆。重点考虑：你自己是否被严重怀疑、你自己是否即将被放逐、继续发言是否会暴露更多狼队信息、是否能阻断关键信息继续流出、立刻结束白天是否比继续留场更赚。若你是最后一名可行动狼人，自爆后没有狼人能继续夜刀，不要幻想「自爆切夜后我还能刀人」。不要因为「队友被怀疑」这一点单独自爆；也不要因为有好人在抗推你就立刻自爆，因为这往往会坐实对方好身份并让剩余队友更难起跳。
{action_hint}"""

    def build_sheriff_nomination_user_prompt(self) -> str:
        role = self.player.role

        # Role-specific guidance
        if role in WOLF_ROLES:
            role_guide = (
                "**狼人上警指南**：\n"
                "- 狼队需要有狼在警上——可以悍跳预言家、可以穿平民控场、也可以穿神职施压。全狼不上警等于把警徽白送给真预言家。\n"
                "- 如果你选择悍跳：前置位悍跳优先给后置位发查杀（力度大于金水）；后置位悍跳被查杀了不要慌，给警下狼队友发金水反打。\n"
                "- 如果你不想悍跳：可以上警穿平民控场（说明你适合带队的原因和投票原则），或者上警穿神职给队友打掩护，后续再退水。\n"
                "- 如果你选择不上警：必须有明确的替代计划（倒钩/深水/冲票），并且想清楚这个计划如何抵消真预言家单边带队的劣势。\n"
                "- 狼队也可以全员不上警打深水生推局（前提是首夜刀中关键神职），或者只派一狼上警诈身份后退水。"
            )
        elif role == Role.SEER:
            role_guide = (
                "**预言家上警指南**：\n"
                "- 你必须上警。不上警的预言家等于放弃了狼人杀最重要的信息传递工具——警徽和警徽流。\n"
                "- 上警后报验人（对象+金水/查杀+验人理由）+ 警徽流（至少2人，覆盖警下摇摆位和焦点位）。"
            )
        elif role == Role.HUNTER:
            role_guide = (
                "**猎人上警指南**：\n"
                "- 猎人可以上警——你有枪兜底，不怕被抗推。可以在警上诈身份（给后置位发查杀观察反应），也可以穿预言家衣服为真预言家挡刀。\n"
                "- 也可以选择不上警，藏在警下投票——猎人的枪是暗牌优势，过早暴露反而让狼队有防备。"
            )
        elif role in (Role.WITCH, Role.GUARD):
            role_guide = (
                "**神职上警建议**：\n"
                "- 女巫和守卫通常不建议上警。藏着活着比什么都重要——你的技能价值远大于在警上多说几句话。\n"
                "- 如果警上已经有多人起跳，你可以上警分析局势，但不要暴露自己的神职身份。"
            )
        else:
            role_guide = (
                "**平民上警指南**：\n"
                "- 平民可以上警，但必须有明确目的：为真预言家挡刀、在警上诈身份、或者分析局势防止狼人单边控场。\n"
                "- 如果没有想好上警要说什么，不如留在警下认真听发言、投好票——警下的一票对真预言家同样重要。\n"
                "- 警上划水（只说「我适合带队」「后面给惊喜」而没有实质内容）是最差的选择——几乎等于给狼人送抗推位。\n"
                "- 「宁愿真预言家拿不到警徽，也不能让狼人拿到警徽」——如果你觉得真预言家可能拿不到警徽，上警可以多一个选择。"
            )

        return f"""现在是首个白天的警长竞选准备阶段。此时昨夜死讯尚未公布：你不知道昨晚是否有人死亡，也不能说「平安夜」。

先核对系统提示里的「最高优先级私有技能事实」、最新狼队夜话和「局内私有便签」，尤其是已确认队友、验人、假身份口径；不要让公开话术覆盖真实私有事实。

{role_guide}

请判断自己是否要上警。若上警，在 public_speech 简短说明竞选理由；若不上警，也保持简短。
action 格式：{{"run_for_sheriff": true/false}}"""

    def build_sheriff_campaign_user_prompt(self, candidates: list[str]) -> str:
        role = self.player.role
        if role in WOLF_ROLES:
            tactic_hint = (
                "**狼人警上发言指南**：\n"
                "- 悍跳预言家：明确说「我昨晚验了X号，是金水/查杀」+ 验人理由 + 警徽流（至少2人）。前置位悍跳优先给后置位发查杀（力度大），后置位悍跳被查杀了不要慌——给警下狼队友发金水反打。\n"
                "- 穿平民控场：说明你为什么适合带队、关注哪些玩家、投票原则——但要意识到在真预言家面前力度不足。\n"
                "- 穿神职施压：暗示自己有神职身份（但不要干拍——暗示即可），为后续起跳留空间。\n"
                "- 如果前置位已有人起跳预言家：判断是队友还是非队友。是非队友→评估对跳收益；是队友→选择配合（冲锋支持）或保持距离（倒钩）。\n"
                "- 实战铁律：悍跳狼玩的就是心态——此刻你就是预言家，发言要果断、不要用「可能」「应该」等模糊词。"
            )
        elif role == Role.SEER:
            tactic_hint = (
                "**预言家警上发言指南**：\n"
                "- 报验人：昨晚验了谁、金水还是查杀、为什么验他。\n"
                "- 留警徽流：至少2人，覆盖警下摇摆位和焦点位，解释为什么选这两人。\n"
                "- 预判对跳：如果后置位有人跟你对跳，他大概率是狼——提前说明你预计的狼人悍跳模式。\n"
                "- 发言要果断——你是全场唯一真预言家，不需要犹豫。"
            )
        elif role in (Role.HUNTER,):
            tactic_hint = (
                "**猎人警上发言指南**：\n"
                "- 如果你在诈身份（给后置位发查杀）：观察对方反应后适时退水，不要死撑。\n"
                "- 如果你在为真预言家挡刀：穿预言家衣服，发言尽量逼真，帮真预言家吸引火力。\n"
                "- 如果你是认真竞选：说明你的分析能力和投票原则。"
            )
        else:
            tactic_hint = (
                "**警上发言指南**：\n"
                "- 说明你为什么上警：挡刀？诈身份？分析局势？\n"
                "- 不要只说「我适合带队」「后面给惊喜」——给不出具体信息就拉不到票。\n"
                "- 如果你是在诈身份（穿预言家衣服给后置位发查杀）：观察对方反应，适时退水。\n"
                "- 如果你是认真竞选：说明你的分析思路和投票原则。"
            )

        return f"""你已经选择上警。当前上警玩家：{self._join_names(candidates)}
{self._live_sheriff_context_block(candidates)}
先核对系统提示里的「最高优先级私有技能事实」、最新狼队夜话和「局内私有便签」，保持你的真实身份判断、确认队友名单和假身份口径一致。

{tactic_hint}

请先参考前面候选人的发言，再发表一段竞选警长的公开发言。action 设为 null。"""

    def build_sheriff_runoff_campaign_user_prompt(self, candidates: list[str], vote_round: int, vote_rounds: list[dict] | None = None) -> str:
        return f"""警长竞选第 {vote_round - 1} 轮出现平票，你仍在 PK 候选人中。当前 PK 候选人：{self._join_names(candidates)}
{self._live_sheriff_context_block(candidates, vote_rounds)}
先核对系统提示里的「最高优先级私有技能事实」和「局内私有便签」，保持你的真实身份判断、确认队友名单和假身份口径一致。
如果你是狼人，请明确你是在延续自己的假身份、补强队友、对跳真预言家，还是有收益地倒钩；不要只用"队友会处理"代替自己的判断。
如果你选择倒钩，请说明它如何服务于后续冲票/刀口/身份收益，而不是单纯站到好人身边。
请补充一段竞选发言，重点回应上一轮票型、解释你为什么比其他平票候选人更适合拿警徽。action 设为 null。"""

    def build_sheriff_vote_user_prompt(self, candidates: list[str], vote_rounds: list[dict] | None = None) -> str:
        return f"""现在是警长投票阶段。只有最初未上警玩家可以投票；上警候选人没有警下投票权。当前可投候选人/PK候选人：{self._join_names(candidates)}
{self._live_sheriff_context_block(candidates, vote_rounds)}
先核对系统提示里的「最高优先级私有技能事实」和「局内私有便签」，不要让公开竞选话术覆盖真实私有事实。
如果你是狼人，投票前比较冲票、倒钩、垫票和保留身份收益；倒钩不是默认答案。
如果你投倒钩票，请说明它带来的身份或票型收益，而不是只因为看起来安全。
请根据警上/PK发言、已有票型和你自己的站边判断投票。
不要长篇复述每个候选人的发言；inner_thought 用 2-3 句写清投票理由即可。
请在这些候选人中选择一人投票，或投给 "abstain"。action 格式：{{"vote_target": "候选人姓名或 abstain"}}"""

    def build_sheriff_guipiao_user_prompt(self) -> str:
        alive_names = [p.name for p in self.alive_other_players]
        return f"""现在是警长归票阶段。作为警长，你刚刚听完所有存活玩家的发言（你最后一个发言）。现在你需要进行归票——给出你建议放逐的目标，并解释理由。

## 归票说明
- 归票是警长对全场的投票建议，你的投票会公开显示给所有玩家。
- 你的归票发言将被所有人听到，之后其他玩家会同时投票（他们知道你投了谁）。
- 请总结本轮讨论的关键信息、你对各玩家的身份判断、以及为什么建议放逐你选中的目标。
- inner_thought 写你的真实判断和归票策略；public_speech 写归票发言。
- 可投目标：{self._join_names(alive_names)}，也可以选择 "abstain" 弃票。
- action 格式：{{"vote_target": "目标姓名或 abstain"}}"""

    def build_sheriff_tiebreak_user_prompt(self, tied_targets: list[str], summary: str) -> str:
        return f"""白天放逐投票出现平票。平票目标：{self._join_names(tied_targets)}
当前票型：{summary}
你是警长，需要在这些平票目标中归票一人。action 格式：{{"vote_target": "平票目标姓名"}}"""

    def build_sheriff_transfer_user_prompt(self, alive_targets: list[str]) -> str:
        return f"""你当前持有警徽，但你即将出局。你可以将警徽移交给一名存活玩家，也可以选择撕毁警徽。可移交目标：{self._join_names(alive_targets)}
action 格式：{{"transfer_badge_target": "玩家名或 null"}}"""

    def build_gun_shot_user_prompt(self, targets: list[str]) -> str:
        return f"""你现在可以开枪带走一名玩家。
可选目标：{self._join_names(targets)}

重要限制：
- 这些目标只是一组可开枪的存活玩家名单，不包含真实身份信息。
- 你不知道任何目标的真实身份，除非该信息来自你的合法秘密信息或已经公开的信息。
- 不要声称"我知道某人是狼"；如果选择目标，只能基于发言、票型、警长竞选、死亡结果等公开线索进行推理。

action 格式：{{"shoot_target": "玩家名"}}"""
