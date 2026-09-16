const TELEGRAM_TOKEN = Deno.env.get("TELEGRAM_TOKEN")!;
const MAX_TOKEN = Deno.env.get("MAX_TOKEN")!;

const TELEGRAM_CHAT = "@dmdznakomstva";
const MAX_API = "https://platform-api2.max.ru";
const PUBLIC_URL = "https://dmd-park-chat-bridge.baranovaee16171.deno.net";
const CHAT_LINK = "https://t.me/dmdznakomstva";

const questionnaires = new Map<number, any>();

async function telegram(method: string, data: unknown = {}) {
  const response = await fetch(
    `https://api.telegram.org/bot${TELEGRAM_TOKEN}/${method}`,
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(data),
    },
  );
  return await response.json();
}

async function maxApi(method: string, data: unknown = {}) {
  const response = await fetch(`${MAX_API}/${method}`, {
    method: "POST",
    headers: {
      Authorization: MAX_TOKEN,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
  return await response.text();
}

function keyboard(buttons: string[][]) {
  return {
    keyboard: buttons.map((row) => row.map((text) => ({text}))),
    resize_keyboard: true,
    one_time_keyboard: true,
  };
}

async function sendQuestion(userId: number, text: string, buttons?: string[][]) {
  const data: any = {chat_id: userId, text};
  if (buttons) data.reply_markup = keyboard(buttons);
  await telegram("sendMessage", data);
}

async function askNext(userId: number) {
  const q = questionnaires.get(userId);
  if (!q) return;

  if (q.step === "name") return sendQuestion(userId, "1️⃣ Как тебя зовут?\n\nНапиши имя или как к тебе обращаться.");
  if (q.step === "age") return sendQuestion(userId, "2️⃣ Сколько тебе лет? 🎂");
  if (q.step === "married") return sendQuestion(userId, "3️⃣ Ты сейчас в браке или отношениях? 💍", [["Да, в браке"], ["Нет"], ["В отношениях"], ["Всё сложно 😄"]]);
  if (q.step === "children") return sendQuestion(userId, "4️⃣ Есть ли у тебя дети? 👶", [["Нет"], ["Да"]]);
  if (q.step === "location") return sendQuestion(userId, "5️⃣ Где ты живёшь? 🏠", [["ДМД Парк"], ["Село Домодедово"], ["Рядом с ДМД Парк"], ["В другом месте"]]);
  if (q.step === "zodiac") return sendQuestion(userId, "6️⃣ Какой у тебя знак зодиака? ♈", [
    ["♈ Овен", "♉ Телец"], ["♊ Близнецы", "♋ Рак"],
    ["♌ Лев", "♍ Дева"], ["♎ Весы", "♏ Скорпион"],
    ["♐ Стрелец", "♑ Козерог"], ["♒ Водолей", "♓ Рыбы"],
  ]);
  if (q.step === "purpose") return sendQuestion(userId, "7️⃣ С какой целью ты пришёл/пришла в чат? 💬", [
    ["❤️ Отношения"], ["👫 Дружба"], ["💬 Общение"],
    ["😏 Знакомства без конкретной цели"], ["👀 Просто посмотреть"],
  ]);
  if (q.step === "friendship") return sendQuestion(userId, "8️⃣ И последний вопрос 😉\n\nКак ты считаешь, существует ли дружба между мужчиной и женщиной?", [
    ["Да ❤️"], ["Нет 😏"], ["Иногда"], ["Зависит от людей"],
  ]);
  if (q.step === "about") return sendQuestion(userId, "9️⃣ И немного о себе 😊\n\nНапиши пару слов о себе. Это необязательный вопрос — можно написать «Пропустить».", [["Пропустить"]]);

  if (q.step === "confirm") {
    const text =
      `❤️ Твоя анкета готова!\n\n` +
      `👤 Имя: ${q.name}\n` +
      `🎂 Возраст: ${q.age}\n` +
      `💍 Статус: ${q.married}\n` +
      `👶 Дети: ${q.children}\n` +
      `🏠 Живёт: ${q.location}\n` +
      `♈ Знак: ${q.zodiac}\n` +
      `❤️ Цель: ${q.purpose}\n` +
      `💬 Дружба между мужчиной и женщиной: ${q.friendship}\n` +
      `📝 О себе: ${q.about || "—"}\n\nВсё верно?`;
    return sendQuestion(userId, text, [["✅ Да, всё верно"], ["✏️ Заполнить заново"]]);
  }
}

async function startQuestionnaire(userId: number) {
  questionnaires.set(userId, {step: "name"});
  await sendQuestion(
    userId,
    "👋 Привет! Добро пожаловать в знакомства ДМД Парк ❤️\n\n" +
    "Мы не хотим, чтобы люди просто сухо залетали в чат со словами «привет» 😄\n\n" +
    "Поэтому сначала немного познакомимся. Анкета небольшая и займёт всего пару минут.\n\n" +
    "После заполнения ты получишь ссылку на чат и сможешь присоединиться уже не совсем незнакомцем 😉",
    [["💬 Заполнить анкету"]],
  );
}

async function handlePrivateMessage(message: any) {
  const userId = message.from?.id;
  const text = message.text?.trim();
  if (!userId || !text) return;

  if (text === "/start") {
    await startQuestionnaire(userId);
    return;
  }

  const q = questionnaires.get(userId);
  if (!q) {
    await startQuestionnaire(userId);
    return;
  }

  if (text === "💬 Заполнить анкету") {
    q.step = "name";
    await askNext(userId);
    return;
  }

  if (q.step === "name") { q.name = text; q.step = "age"; }
  else if (q.step === "age") { q.age = text; q.step = "married"; }
  else if (q.step === "married") { q.married = text; q.step = "children"; }
  else if (q.step === "children") { q.children = text; q.step = "location"; }
  else if (q.step === "location") { q.location = text; q.step = "zodiac"; }
  else if (q.step === "zodiac") { q.zodiac = text; q.step = "purpose"; }
  else if (q.step === "purpose") { q.purpose = text; q.step = "friendship"; }
  else if (q.step === "friendship") { q.friendship = text; q.step = "about"; }
  else if (q.step === "about") { q.about = text === "Пропустить" ? "" : text; q.step = "confirm"; }
  else if (q.step === "confirm") {
    if (text === "✏️ Заполнить заново") {
      await startQuestionnaire(userId);
      return;
    }

    if (text === "✅ Да, всё верно") {
      q.completed = true;
      q.profile =
        `🎉 Новый участник в знакомствах ДМД Парк!\n\n` +
        `👤 ${q.name}, ${q.age}\n` +
        `💍 ${q.married}\n` +
        `👶 Дети: ${q.children}\n` +
        `🏠 ${q.location}\n` +
        `♈ ${q.zodiac}\n` +
        `❤️ ${q.purpose}\n` +
        `💬 Дружба: ${q.friendship}\n` +
        `📝 ${q.about || "О себе ничего не указано"}`;

      await telegram("sendMessage", {
        chat_id: userId,
        text:
          `Готово! ❤️\n\n` +
          `Теперь можно присоединиться к чату знакомств ДМД Парк.\n\n` +
          `После входа твоя анкета автоматически появится в чате. 👇\n\n${CHAT_LINK}`,
        reply_markup: {remove_keyboard: true},
      });
      return;
    }
  }

  await askNext(userId);
}

async function handleTelegram(update: any) {
  if (update.message?.new_chat_members) {
    for (const member of update.message.new_chat_members) {
      const q = questionnaires.get(member.id);
      if (!q?.completed || !q.profile) continue;

      await telegram("sendMessage", {
        chat_id: update.message.chat.id,
        text: q.profile,
      });
      questionnaires.delete(member.id);
    }
    return;
  }

  const message = update.message;
  if (!message) return;

  if (message.chat?.type === "private") {
    await handlePrivateMessage(message);
    return;
  }

  if (message.chat?.username !== "dmdznakomstva") return;
  if (message.from?.is_bot) return;

  const text = message.text;
  if (!text) return;

  const name =
    `${message.from?.first_name ?? ""} ${message.from?.last_name ?? ""}`.trim() || "Сосед";

  console.log(`Telegram group message from ${name}: ${text}`);
}

async function handleMax(update: any) {
  if (update.update_type !== "message_created") return;

  const message = update.message ?? {};
  const sender = message.sender ?? update.sender ?? {};
  if (sender.is_bot) return;

  const text = message.body?.text ?? message.text;
  if (!text) return;

  await telegram("sendMessage", {
    chat_id: TELEGRAM_CHAT,
    text: `👋 ${sender.name || "Сосед"} • MAX\n\n${text}`,
  });
}

async function setupWebhooks() {
  await telegram("setWebhook", {
    url: `${PUBLIC_URL}/telegram/webhook`,
    allowed_updates: ["message"],
  });

  try {
    await fetch(`${MAX_API}/subscriptions`, {
      method: "POST",
      headers: {
        Authorization: MAX_TOKEN,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        url: `${PUBLIC_URL}/max/webhook`,
        update_types: ["message_created", "bot_added"],
      }),
    });
  } catch (error) {
    console.error("MAX webhook error:", error);
  }
}

await setupWebhooks();

Deno.serve(async (request) => {
  if (request.method === "GET") {
    return new Response("DMD Park Chat Bridge is running!");
  }

  try {
    const update = await request.json();
    const url = new URL(request.url);

    if (url.pathname === "/telegram/webhook") {
      await handleTelegram(update);
    }

    if (url.pathname === "/max/webhook") {
      await handleMax(update);
    }

    return Response.json({ok: true});
  } catch (error) {
    console.error(error);
    return Response.json(
      {ok: false, error: String(error)},
      {status: 500},
    );
  }
});
