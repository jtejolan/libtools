const bookQuotes = [
  {
    quote: "Call me Ishmael.",
    title: "Moby-Dick",
    author: "Herman Melville",
  },
  {
    quote:
      "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.",
    title: "Pride and Prejudice",
    author: "Jane Austen",
  },
  {
    quote: "There is no charm equal to tenderness of heart.",
    title: "Emma",
    author: "Jane Austen",
  },
  {
    quote:
      "I am no bird; and no net ensnares me: I am a free human being with an independent will.",
    title: "Jane Eyre",
    author: "Charlotte Brontë",
  },
  {
    quote: "Whatever our souls are made of, his and mine are the same.",
    title: "Wuthering Heights",
    author: "Emily Brontë",
  },
  {
    quote: "Beware; for I am fearless, and therefore powerful.",
    title: "Frankenstein",
    author: "Mary Shelley",
  },
  {
    quote:
      "Nothing is so painful to the human mind as a great and sudden change.",
    title: "Frankenstein",
    author: "Mary Shelley",
  },
  {
    quote:
      "Nowadays people know the price of everything and the value of nothing.",
    title: "The Picture of Dorian Gray",
    author: "Oscar Wilde",
  },
  {
    quote:
      "The sun himself is weak when he first rises, and gathers strength and courage as the day gets on.",
    title: "The Old Curiosity Shop",
    author: "Charles Dickens",
  },
  {
    quote:
      "No one is useless in this world who lightens the burdens of another.",
    title: "Our Mutual Friend",
    author: "Charles Dickens",
  },
  {
    quote:
      "I wish, as well as everybody else, to be perfectly happy; but, like everybody else, it must be in my own way.",
    title: "Sense and Sensibility",
    author: "Jane Austen",
  },
];

const quote = bookQuotes[Math.floor(Math.random() * bookQuotes.length)];

document.querySelector("#book-quote-text").textContent = quote.quote;
document.querySelector("#book-quote-title").textContent = quote.title;
document.querySelector("#book-quote-author").textContent = quote.author;
