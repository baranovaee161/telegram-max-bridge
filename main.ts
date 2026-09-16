const TELEGRAM_TOKEN = Deno.env.get("TELEGRAM_TOKEN")!;
const MAX_TOKEN = Deno.env.get("MAX_TOKEN")!;

const TELEGRAM_CHAT = "@dmdznakomstva";
const MAX_API = "https://platform-api2.max.ru";

const PUBLIC_URL =
  "https://dmd-park-chat-bridge.baranovaee16171.deno.net";

const CHAT_LINK = "https://t.me/dmdznakomstva";

const questionnaires = new Map<number, any>();

async function telegram(method: string, data: unknown = {}) {
  const response = await fetch(
    `https://api.telegram.org/bot${TELEGRAM_TOKEN}/${method}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    },
  );

  const result = await response.json();
  console.log("Telegram:", result);
  return result;
}

async function maxApi(
  method: string,
  data: unknown = {},
  params: Record<string, string> = {},
) {
  const url = new URL(`${MAX_API}/${method}`);

  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: MAX_TOKEN,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });

  const text = await response.text();

  console.log("MAX:", response.status, text);

  return text;
}

async function sendToTelegram(text: string) {
  return telegram("sendMessage", {
    chat_id: TELEGRAM_CHAT,
    text,
  });
}

async function sendToMax(text: string) {
  console.log("MAX message:", text);
}

function keyboard(buttons: string[][]) {
  return {
    keyboard: buttons.map((row) =>
      row.map((text) => ({
        text,
      })),
    ),
    resize_keyboard: true,
    one_time_keyboard: true,
  };
}

async function startQuestionnaire(userId: number) {
  questionnaires.set(userId, {
    step: "name",
  });

  await telegram("sendMessage", {
    chat_id: userId,
    text:
      "👋 Привет! Добро пожаловать в знакомства ДМД Парк ❤️\n\n" +
      "Мы не хотим, чтобы люди просто сухо залетали в чат со словами «привет» 😄\n\n" +
      "Поэтому сначала немного познакомимся. " +
      "Анкета небольшая и займёт всего пару минут.\n\n" +
      "После заполнения ты получишь ссылку на чат и сможешь присоединиться уже не совсем незнакомцем 😉",
    reply_markup: keyboard([
      ["💬 Заполнить анкету"],
    ]),
  });
}

async function askNext(userId: number) {
  const q = questionnaires.get(userId);

  if (!q) return;

  if (q.step === "name") {
    await telegram("sendMessage", {
      chat_id: userId,
      text:
        "1️⃣ Как тебя зовут?\n\nНапиши имя или как к тебе обращаться.",
    });
    return;
  }

  if (q.step === "age") {
    await telegram("sendMessage", {
      chat_id: userId,
      text: "2️⃣ Сколько тебе лет? 🎂",
    });
    return;
  }

  if (q.step === "married") {
    await telegram("sendMessage", {
      chat_id: userId,
      text: "3️⃣ Ты сейчас в браке или отношениях? 💍",
      reply_markup: keyboard([
        ["Да, в браке"],
        ["Нет"],
        ["В отношениях"],
        ["Всё сложно 😄"],
      ]),
    });
    return;
  }

  if (q.step === "children") {
    await telegram("sendMessage", {
      chat_id: userId,
      text: "4️⃣ Есть ли у тебя дети? 👶",
      reply_markup: keyboard([
        ["Нет"],
        ["Да"],
      ]),
    });
    return;
  }

  if (q.step === "location") {
    await telegram("sendMessage", {
      chat_id: userId,
      text: "5️⃣ Где ты живёшь? 🏠",
      reply_markup: keyboard([
        ["ДМД Парк"],
        ["Село Домодедово"],
        ["Рядом с ДМД Парк"],
        ["В другом месте"],
      ]),
    });
    return;
  }

  if (q.step === "zodiac") {
    await telegram("sendMessage", {
      chat_id: userId,
      text: "6️⃣ Какой у тебя знак зодиака? ♈",
      reply_markup: keyboard([
        ["♈ Овен", "♉ Телец"],
        ["♊ Близнецы", "♋ Рак"],
        ["♌ Лев", "♍ Дева"],
        ["♎ Весы", "♏ Скорпион"],
        ["♐ Стрелец", "♑ Козерог"],
        ["♒ Водолей", "♓ Рыбы"],
      ]),
    });
    return;
  }

  if (q.step === "purpose") {
    await telegram("sendMessage", {
      chat_id: userId,
      text: "7️⃣ С какой целью ты пришёл/пришла в чат? 💬",
      reply_markup: keyboard([
        ["❤️ Отношения"],
        ["👫 Дружба"],
        ["💬 Общение"],
        ["😏 Знакомства без конкретной цели"],
        ["👀 Просто посмотреть"],
      ]),
    });
    return;
  }

  if (q.step === "friendship") {
    await telegram("sendMessage", {
      chat_id: userId,
      text:
        "8️⃣ И последний вопрос 😉\n\n" +
        "Как ты считаешь, существует ли дружба между мужчиной и женщиной?",
      reply_markup: keyboard([
        ["Да ❤️"],
        ["Нет 😏"],
        ["Иногда"],
        ["Зависит от людей"],
      ]),
    });
    return;
  }

  if (q.step === "about") {
    await telegram("sendMessage", {
      chat_id: userId,
      text:
        "9️⃣ И немного о себе 😊\n\n" +
        "Напиши пару слов о себе. Это необязательный вопрос — можно написать «Пропустить».",
      reply_markup: keyboard([
        ["Пропустить"],
      ]),
    });
    return;
  }

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
      `📝 О себе: ${q.about || "—"}\n\n` +
      `Всё верно?`;

    await telegram("sendMessage", {
      chat_id: userId,
      text,
      reply_markup: keyboard([
        ["✅ Да, всё верно"],
        ["✏️ Заполнить заново"],
      ]),
    });
  }
}

async function handlePrivateMessage(message: any) {
  const userId = message.from?.id;

  if (!userId) return;

  const text = message.text?.trim();

  if (!text) return;

  if (text === "/start") {
    await startQuestionnaire(userId);
    return;
  }

  if (text === "💬 Заполнить анкету") {
    await startQuestionnaire(userId);

    const q = questionnaires.get(userId);

    if (q) {
      q.step = "name";
      await askNext(userId);
    }

    return;
  }

  const q = questionnaires.get(userId);

  if (!q) {
    await startQuestionnaire(userId);
    return;
  }

  if (q.step === "name") {
    q.name = text;
    q.step = "age";
    await askNext(userId);
    return;
  }

  if (q.step === "age") {
    q.age = text;
    q.step = "married";
    await askNext(userId);
    return;
  }

  if (q.step === "married") {
    q.married = text;
    q.step = "children";
    await askNext(userId);
    return;
  }

  if (q.step === "children") {
    q.children = text;
    q.step = "location";
    await askNext(userId);
    return;
  }

  if (q.step === "location") {
    q.location = text;
    q.step = "zodiac";
    await askNext(userId);
    return;
  }

  if (q.step === "zodiac") {
    q.zodiac = text;
    q.step = "purpose";
    await askNext(userId);
    return;
  }

  if (q.step === "purpose") {
    q.purpose = text;
    q.step = "friendship";
    await askNext(userId);
    return;
  }

  if (q.step === "friendship") {
    q.friendship = text;
    q.step = "about";
    await askNext(userId);
    return;
  }

  if (q.step === "about") {
    q.about = text === "Пропустить" ? "" : text;
    q.step = "confirm";
    await askNext(userId);
    return;
  }

  if (q.step === "confirm") {
    if (text === "✏️ Заполнить заново") {
      await startQuestionnaire(userId);
      await askNext(userId);
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
          `После входа твоя анкета автоматически появится в чате. 👇\n\n` +
          CHAT_LINK,
        reply_markup: {
          remove_keyboard: true,
        },
      });
    }
  }
}

async function handleTelegram(update: any) {
  console.log(
    "TELEGRAM UPDATE:",
    JSON.stringify(update),
  );

  if (update.message?.new_chat_members) {
    for (const member of update.message.new_chat_members) {
      const userId = member.id;
      const q = questionnaires.get(userId);

      if (!q?.completed || !q.profile) {
        continue;
      }

      await telegram("sendMessage", {
        chat_id: update.message.chat.id,
        text: q.profile,
      });

      questionnaires.delete(userId);
    }

    return;
  }

  const message = update.message;

  if (!message) return;

  const chat = message.chat ?? {};

  if (chat.type === "private") {
    await handlePrivateMessage(message);
    return;
  }

  if (chat.username !== "dmdznakomstva") return;

  const sender = message.from ?? {};

  if (sender.is_bot) return;

  const text = message.text;

  if (!text) return;

  const name =
    `${sender.first_name ?? ""} ${sender.last_name ?? ""}`.trim() ||
    "Сосед";

  await sendToMax(
    `👋 ${name} • Telegram\n\n${text}`,
  );
}

async function handleMax(update: any) {
  console.log(
    "MAX UPDATE:",
    JSON.stringify(update),
  );

  if (update.update_type !== "message_created") {
    return;
  }

  const message = update.message ?? {};

  const sender =
    message.sender ??
    update.sender ??
    {};

  if (sender.is_bot) return;

  const text =
    message.body?.text ??
    message.text;

  if (!text) return;

  const name =
    sender.name ||
    "Сосед";

  await sendToTelegram(
    `👋 ${name} • MAX\n\n${text}`,
  );
}

async function setupWebhooks() {
  console.log("Настраиваем webhooks...");

  await telegram(
    "setWebhook",
    {
      url: `${PUBLIC_URL}/telegram/webhook`,
      allowed_updates: [
        "message",
      ],
    },
  );

  try {
    const response = await fetch(
      `${MAX_API}/subscriptions`,
      {
        method: "POST",
        headers: {
          Authorization: MAX_TOKEN,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          url: `${PUBLIC_URL}/max/webhook`,
          update_types: [
            "message_created",
            "bot_added",
          ],
        }),
      },
    );

    console.log(
      "MAX webhook:",
      response.status,
      await response.text(),
    );
  } catch (error) {
    console.error(
      "MAX webhook error:",
      error,
    );
  }
}

await setupWebhooks();

Deno.serve(async (request) => {
  if (request.method === "GET") {
    return new Response(
      "DMD Park Chat Bridge is running!",
    );
  }

  const url = new URL(request.url);

  try {
    const update = await request.json();

    if (
      url.pathname ===
      "/telegram/webhook"
    ) {
      await handleTelegram(update);
    }

    if (
      url.pathname ===
      "/max/webhook"
    ) {
      await handleMax(update);
    }

    return Response.json({
      ok: true,
    });
  } catch (error) {
    console.error(error);

    return Response.json(
      {
        ok: false,
        error: String(error),
      },
      {
        status: 500,
      },
    );
  }
});
