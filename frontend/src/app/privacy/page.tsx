import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { BrandMark } from "@/components/brand-mark";
import { SectionHeading } from "@/components/section-heading";

export const metadata: Metadata = {
  title: "Политика данных — Developer Profile Platform",
};

// A draft from the system's facts (ADR-0020, ADR-0026, ADR-0028, ADR-0029). The operator
// and the address are filled in by the owner, and a lawyer checks the text,
// before the launch (step 9.8).
const OPERATOR = "[оператор — заполнить до запуска]";
const CONTACT = "[адрес для обращений — заполнить до запуска]";

const SECTIONS: { id: string; title: string; body: ReactNode }[] = [
  {
    id: "collect",
    title: "Что мы храним",
    body: (
      <ul className="flex list-disc flex-col gap-2 pl-6">
        <li>
          Из GitHub при входе: id и логин, аватар и email, если он открыт в GitHub. Email из GitHub
          нигде не публикуется.
        </li>
        <li>Профиль: имя, заголовок, «О себе», локацию и контакты, которые вы добавили.</li>
        <li>
          Проекты: тексты, технологии, ссылку на демо и скриншоты. Метаданные снимков (EXIF, в том
          числе геолокация) удаляются при загрузке.
        </li>
        <li>
          Привязанные публичные репозитории и их данные из GitHub: название, описание, языки, дату
          последнего изменения, признаки форка и архива, а также кто вы в репозитории — владелец или
          участник.
        </li>
      </ul>
    ),
  },
  {
    id: "public",
    title: "Что видят другие",
    body: (
      <>
        <p>
          Посетителям виден только опубликованный профиль и опубликованные публичные проекты.
          Скрытый профиль, черновики и закрытые проекты не видны никому, кроме вас.
        </p>
        <p>
          Telegram, LinkedIn и другие ссылки показываются на странице профиля. Email и телефон
          показываются посетителю только после нажатия на кнопку и не попадают в код страницы.
        </p>
      </>
    ),
  },
  {
    id: "technical",
    title: "Технические данные",
    body: (
      <>
        <p>
          Cookie сессии нужна для входа и живёт до 14 дней. Рекламы и сторонних трекеров нет.
        </p>
        <p>
          Владелец профиля видит, сколько раз за день открывали его профиль и проекты и нажимали
          на демо, GitHub и контакты. Хранятся только эти суммы за день: без IP, cookie и
          каких-либо данных о посетителе. Свои просмотры владельца не считаются.
        </p>
        <p>
          IP-адреса запросов попадают в журналы сервера и хранятся, пока журналы не перезапишутся
          более новыми. По IP ограничивается частота входа, открытия контактов и отправки
          счётчиков; эти счётчики хранятся только в памяти сервера.
        </p>
      </>
    ),
  },
  {
    id: "others",
    title: "Кому передаются данные",
    body: (
      <ul className="flex list-disc flex-col gap-2 pl-6">
        <li>GitHub — для входа и чтения публичных данных привязанных репозиториев.</li>
        <li>Хранилище резервных копий — в зашифрованном виде.</li>
        <li>Сервис мониторинга получает только сигналы «работает» и «сбой», без данных о вас.</li>
      </ul>
    ),
  },
  {
    id: "retention",
    title: "Сроки и удаление",
    body: (
      <>
        <p>
          Данные хранятся, пока существует аккаунт. Удалить его можно в кабинете, в разделе
          «Удаление аккаунта»: профиль, контакты, проекты и скриншоты удаляются сразу.
        </p>
        <p>
          В резервных копиях удалённые данные остаются до 6 месяцев, пока копии не заменятся
          новыми.
        </p>
        <p>
          Доступ приложения к GitHub отзывается отдельно, в{" "}
          <a
            href="https://github.com/settings/applications"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-4"
          >
            настройках GitHub
          </a>
          .
        </p>
      </>
    ),
  },
  {
    id: "operator",
    title: "Оператор и обращения",
    body: (
      <p>
        Оператор: {OPERATOR}. Вопросы о данных и требования об их удалении: {CONTACT}.
      </p>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-8 p-6">
      <header>
        <Link href="/" aria-label="На главную">
          <BrandMark />
        </Link>
      </header>
      <main className="flex flex-col gap-8">
        <h1 className="font-heading text-2xl leading-relaxed uppercase">Политика данных</h1>
        {SECTIONS.map((section) => (
          <section
            key={section.id}
            aria-labelledby={`privacy-${section.id}`}
            className="flex flex-col gap-4"
          >
            <SectionHeading id={`privacy-${section.id}`} marker="label">
              {section.title}
            </SectionHeading>
            <div className="flex flex-col gap-3 bg-panel px-8 py-6 text-lg leading-relaxed shadow-panel">
              {section.body}
            </div>
          </section>
        ))}
      </main>
    </div>
  );
}
