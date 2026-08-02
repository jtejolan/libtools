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
  {
    quote: "There is some good in this world, and it’s worth fighting for.",
    title: "The Two Towers",
    author: "J.R.R. Tolkien",
  },
  {
    quote: "It is only with the heart that one can see rightly; what is essential is invisible to the eye.",
    title: "The Little Prince",
    author: "Antoine de Saint-Exupéry",
  },
  {
    quote: "I am no bird; and no net ensnares me: I am a free human being with an independent will, which I now exert to leave you.",
    title: "Jane Eyre",
    author: "Charlotte Brontë",
  },
  {
    quote: "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of foolishness, it was the epoch of belief, it was the epoch of incredulity, it was the season of Light, it was the season of Darkness, it was the spring of hope, it was the winter of despair.",
    title: "A Tale of Two Cities",
    author: "Charles Dickens",
  },
  {
    quote: "Beware; for I am fearless, and therefore powerful.",
    title: "Frankenstein",
    author: "Mary Shelley",
  },
  {
    quote: "I wanted you to see what real courage is, instead of getting the idea that courage is a man with a gun in his hand. It’s when you know you’re licked before you begin but you begin anyway and you see it through no matter what. You rarely win, but sometimes you do.",
    title: "To Kill a Mockingbird",
    author: "Harper Lee",
  },
  {
    quote: "A man, after he has brushed off the dust and chips of his life, will have left only the hard, clean questions: Was it good or was it evil? Have I done well — or ill?",
    title: "East of Eden",
    author: "John Steinbeck",
  },
  {
    quote: "The only way out of the labyrinth of suffering is to forgive.",
    title: "Looking for Alaska",
    author: "John Green",
  },
  {
    quote: "This above all: To thine own self be true, And it must follow, as the night the day, Thou canst not then be false to any man.",
    title: "Hamlet",
    author: "William Shakespeare",
  },
  {
    quote: "‘Why did you do all this for me?’ he asked. ‘I don’t deserve it. I’ve never done anything for you.’ ‘You have been my friend,’ replied Charlotte. ‘That in itself is a tremendous thing.’",
    title: "Charlotte’s Web",
    author: "E.B. White",
  },
  {
    quote: "I took a deep breath and listened to the old brag of my heart: I am, I am, I am.",
    title: "The Bell Jar",
    author: "Sylvia Plath",
  },
  {
    quote: "Love is or it ain’t. Thin love ain’t love at all.",
    title: "Beloved",
    author: "Toni Morrison",
  },
  {
    quote: "We accept the love we think we deserve.",
    title: "The Perks of Being a Wallflower",
    author: "Stephen Chbosky",
  },
  {
    quote: "And so we beat on, boats against the current, borne back ceaselessly into the past.",
    title: "The Great Gatsby",
    author: "F. Scott Fitzgerald",
  },
  {
    quote: "Generally, by the time you are Real, most of your hair has been loved off, and your eyes drop out and you get loose in the joints and very shabby. But these things don’t matter at all, because once you are Real you can’t be ugly, except to people who don’t understand.",
    title: "Velveteen Rabbit",
    author: "Margery Williams",
  },
  {
    quote: "Ever’body’s askin’ that. ‘What we comin’ to?’ Seems to me we don’t never come to nothin’. Always on the way.",
    title: "The Grapes of Wrath",
    author: "John Steinbeck",
  },
  {
    quote: "Whatever our souls are made of, his and mine are the same.",
    title: "Wuthering Heights",
    author: "Emily Brontë",
  },
  {
    quote: "There are years that ask questions and years that answer.",
    title: "Their Eyes Were Watching God",
    author: "Zora Neale Hurston",
  },
  {
    quote: "I am not afraid of storms, for I am learning how to sail my ship.",
    title: "Little Women",
    author: "Louisa May Alcott",
  },
  {
    quote: "All happy families are alike; each unhappy family is unhappy in its own way.",
    title: "Anna Karenina",
    author: "Leo Tolstoy",
  },
  {
    quote: "Memories warm you up from the inside. But they also tear you apart.",
    title: "Kafka on the Shore",
    author: "Haruki Murakami",
  },
  {
    quote: "It is nothing to die; it is dreadful not to live.",
    title: "Les Misérables",
    author: "Victor Hugo",
  },
  {
    quote: "Who controls the past controls the future. Who controls the present controls the past.",
    title: "Nineteen Eighty-Four",
    author: "George Orwell",
  },
  {
    quote: "Life is to be lived, not controlled; and humanity is won by continuing to play in face of certain defeat.",
    title: "Invisible Man",
    author: "Ralph Ellison",
  },
  {
    quote: "Last night I dreamt I went to Manderley again.",
    title: "Rebecca",
    author: "Daphne du Maurier",
  },
  {
    quote: "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.",
    title: "Pride and Prejudice",
    author: "Jane Austen",
  },
  {
    quote: "Tomorrow I’ll think of some way to get him back. After all, tomorrow is another day.",
    title: "Gone with the Wind",
    author: "Margaret Mitchell",
  },
  {
    quote: "Why, sometimes, I’ve believed as many as six impossible things before breakfast.",
    title: "Through the Looking-Glass",
    author: "Lewis Carroll",
  },
  {
    quote: "Don’t ever tell anybody anything. If you do, you start missing everybody.",
    title: "The Catcher in the Rye",
    author: "J. D. Salinger",
  },
  {
    quote: "It does not do to dwell on dreams and forget to live.",
    title: "Harry Potter and the Sorcerer’s Stone",
    author: "J.K. Rowling",
  },
  {
    quote: "You pierce my soul. I am half agony. Half hope. Tell me not that I am too late, that such precious feelings are gone for ever.",
    title: "Persuasion",
    author: "Jane Austen",
  },
  {
    quote: "So it goes…",
    title: "Slaughterhouse-Five",
    author: "Kurt Vonnegut",
  },
  {
    quote: "I had the epiphany that laughter was light, and light was laughter, and that this was the secret of the universe.",
    title: "The Goldfinch",
    author: "Donna Tartt",
  },
  {
    quote: "There are some things you learn best in calm, and some in storm.",
    title: "The Song of the Lark",
    author: "Willa Cather",
  },
  {
    quote: "When you play the game of thrones you win or you die.",
    title: "A Game of Thrones",
    author: "George R. R. Martin",
  },
  {
    quote: "The world breaks everyone, and afterward, many are strong at the broken places.",
    title: "A Farewell to Arms",
    author: "Ernest Hemingway",
  },
  {
    quote: "From that time on, the world was hers for the reading. She would never be lonely again, never miss the lack of intimate friends. Books became her friends and there was one for every mood.",
    title: "A Tree Grows in Brooklyn",
    author: "Betty Smith",
  },
  {
    quote: "Once upon a time there was a boy who loved a girl, and her laughter was a question he wanted to spend his whole life answering.",
    title: "The History of Love",
    author: "Nicole Krauss",
  },
  {
    quote: "Very few castaways can claim to have survived so long at sea as Mr. Patel, and none in the company of an adult Bengal tiger.",
    title: "Life of Pi",
    author: "Yann Martel",
  },
  {
    quote: "Anyone who ever gave you confidence, you owe them a lot.",
    title: "Breakfast at Tiffany’s",
    author: "Truman Capote",
  },
  {
    quote: "Isn’t it nice to think that tomorrow is a new day with no mistakes in it yet?",
    title: "Anne of Green Gables",
    author: "L. M. Montgomery",
  },
  {
    quote: "You forget what you want to remember, and you remember what you want to forget.",
    title: "The Road",
    author: "Cormac McCarthy",
  },
  {
    quote: "Call me Ishmael.",
    title: "Moby Dick",
    author: "Herman Melville",
  },
  {
    quote: "It was a pleasure to burn.",
    title: "Fahrenheit 451",
    author: "Ray Bradbury",
  },
  {
    quote: "The past is not dead. In fact, it’s not even past.",
    title: "Requiem for a Nun",
    author: "William Faulkner",
  },
  {
    quote: "He has put a knife on the things that held us together and we have fallen apart.",
    title: "Things Fall Apart",
    author: "Chinua Achebe",
  },
  {
    quote: "’And now,’ cried Max, ‘let the wild rumpus start!’",
    title: "Where the Wild Things Are",
    author: "Maurice Sendak",
  },
  {
    quote: "Memories, even your most precious ones, fade surprisingly quickly. But I don’t go along with that. The memories I value most, I don’t ever see them fading.",
    title: "Never Let Me Go",
    author: "Kazuo Ishiguro",
  },
  {
    quote: "Nowadays people know the price of everything and the value of nothing.",
    title: "The Picture of Dorian Grey",
    author: "Oscar Wilde",
  },
  {
    quote: "Time is the longest distance between two places.",
    title: "The Glass Menagerie",
    author: "Tennessee Williams",
  },
  {
    quote: "The voice of the sea is seductive, never ceasing, whispering, clamoring, murmuring, inviting the soul to wander in abysses of solitude.",
    title: "The Awakening",
    author: "Kate Chopin",
  },
  {
    quote: "We dream in our waking moments, and walk in our sleep.",
    title: "The Scarlet Letter",
    author: "Nathaniel Hawthorne",
  },
  {
    quote: "The place where you made your stand never mattered. Only that you were there… and still on your feet.",
    title: "The Stand",
    author: "Stephen King",
  },
  {
    quote: "But soft! What light through yonder window breaks? It is the east, and Juliet is the sun.",
    title: "Romeo and Juliet",
    author: "William Shakespeare",
  },
  {
    quote: "My advice is, never do tomorrow what you can do today. Procrastination is the thief of time.",
    title: "David Copperfield",
    author: "Charles Dickens",
  },
  {
    quote: "So many things are possible just as long as you don’t know they’re impossible.",
    title: "The Phantom Tollbooth",
    author: "Norton Juster",
  },
  {
    quote: "I can’t stand it to think my life is going so fast and I’m not really living it.",
    title: "The Sun Also Rises",
    author: "Ernest Hemingway",
  },
  {
    quote: "Only the margin left to write on now. I love you, I love you, I love you.",
    title: "I Capture the Castle",
    author: "Dodie Smith",
  },
  {
    quote: "It doesn’t matter who you are or what you look like, so long as somebody loves you.",
    title: "The Witches",
    author: "Roald Dahl",
  },
  {
    quote: "The same substance composes us — the tree overhead, the stone beneath us, the bird, the beast, the star — we are all one, all moving to the same end.",
    title: "Mary Poppins",
    author: "P.L. Travers",
  },
  {
    quote: "I wish, as well as everybody else, to be perfectly happy; but, like everybody else, it must be in my own way.",
    title: "Sense and Sensibility",
    author: "Jane Austen",
  },
  {
    quote: "Love is holy because it is like grace – the worthiness of its object is never really what matters.",
    title: "Gilead",
    author: "Marilynne Robinson",
  },
  {
    quote: "Each time you happen to me all over again.",
    title: "The Age of Innocence",
    author: "Edith Wharton",
  },
  {
    quote: "Brave doesn’t mean you’re not scared. It means you go on even though you’re scared.",
    title: "The Hate U Give",
    author: "Angie Thomas",
  },
  {
    quote: "How easy it was to lie to strangers, to create with strangers the versions of our lives we imagined.",
    title: "Americanah",
    author: "Chimamanda Ngozi Adichie",
  },
  {
    quote: "And, when you want something, all the universe conspires in helping you to achieve it.",
    title: "The Alchemist",
    author: "Paulo Coelho",
  },
  {
    quote: "Life, with its rules, its obligations, and its freedoms, is like a sonnet: You’re given the form, but you have to write the sonnet yourself.",
    title: "A Wrinkle in Time",
    author: "Madeleine L’Engle",
  },
  {
    quote: "There is always something left to love.",
    title: "One Hundred Years of Solitude",
    author: "Gabriel García Márquez",
  },
  {
    quote: "The answer to the ultimate question of life, the universe and everything is 42.",
    title: "The Hitchhiker’s Guide to the Galaxy",
    author: "Douglas Adams",
  },
  {
    quote: "All the world’s a stage, and all the men and women merely players. They have their exits and their entrances; And one man in his time plays many parts.",
    title: "As You Like It",
    author: "William Shakespeare",
  },
  {
    quote: "Stay gold, Ponyboy, stay gold.",
    title: "The Outsiders",
    author: "S. E. Hinton",
  },
  {
    quote: "Sometimes I can hear my bones straining under the weight of all the lives I’m not living.",
    title: "Extremely Loud and Incredibly Close",
    author: "Jonathan Safran Foer",
  },
  {
    quote: "Do I love you? My God, if your love were a grain of sand, mine would be a universe of beaches.",
    title: "The Princess Bride",
    author: "William Goldman",
  },
  {
    quote: "Time moves slowly, but passes quickly.",
    title: "The Color Purple",
    author: "Alice Walker",
  },
  {
    quote: "You don’t know about me without you have read a book by the name of The Adventures of Tom Sawyer, but that ain’t no matter.",
    title: "The Adventures of Huckleberry Finn",
    author: "Mark Twain",
  },
  {
    quote: "Love is the longing for the half of ourselves we have lost.",
    title: "The Unbearable Lightness of Being",
    author: "Milan Kundera",
  },
  {
    quote: "It is our choices, Harry, that show what we truly are, far more than our abilities.",
    title: "Harry Potter and the Chamber of Secrets",
    author: "J.K. Rowling",
  },
  {
    quote: "For you, a thousand times over.",
    title: "The Kite Runner",
    author: "Khaled Hosseini",
  },
  {
    quote: "Then you must teach my daughter this same lesson. How to lose your innocence but not your hope. How to laugh forever.",
    title: "The Joy Luck Club",
    author: "Amy Tan",
  },
  {
    quote: "And may the odds be ever in your favor.",
    title: "The Hunger Games",
    author: "Suzanne Collins",
  },
  {
    quote: "Ralph wept for the end of innocence, the darkness of man’s heart, and the fall through the air of the true, wise friend called Piggy.",
    title: "Lord of the Flies",
    author: "William Golding",
  },
  {
    quote: "All human wisdom is summed up in these two words – ‘Wait and hope.’",
    title: "The Count of Monte Cristo",
    author: "Alexandre Dumas",
  },
  {
    quote: "Oh, the places you’ll go! You’ll be on your way up! You’ll be seeing great sights! You’ll join the high fliers who soar to high heights.",
    title: "Oh, the Places You’ll Go",
    author: "Dr. Seuss",
  },
  {
    quote: "The longer I live, the more uninformed I feel. Only the young have an explanation for everything.",
    title: "City of the Beasts",
    author: "Isabel Allende",
  },
  {
    quote: "Open your eyes and see what you can with them before they close forever.",
    title: "All the Light We Cannot See",
    author: "Anthony Doerr",
  },
  {
    quote: "If you have the guts to be yourself, other people’ll pay your price.",
    title: "Rabbit, Run",
    author: "John Updike",
  },
  {
    quote: "We were the people who were not in the papers. We lived in the blank white spaces at the edges of print. It gave us more freedom. We lived in the gaps between the stories.",
    title: "The Handmaid’s Tale",
    author: "Margaret Atwood",
  },
  {
    quote: "As Gregor Samsa awoke one morning from uneasy dreams he found himself transformed in his bed into an enormous insect.",
    title: "The Metamorphosis",
    author: "Franz Kafka",
  },
  {
    quote: "What does the brain matter compared with the heart?",
    title: "Mrs. Dalloway",
    author: "Virginia Woolf",
  },
  {
    quote: "We are such stuff as dreams are made on, and our little life is rounded with a sleep.",
    title: "The Tempest",
    author: "William Shakespeare",
  },
  {
    quote: "The creatures outside looked from pig to man, and from man to pig, and from pig to man again; but already it was impossible to say which was which.",
    title: "Animal Farm",
    author: "George Orwell",
  },
  {
    quote: "Most men and women will grow up to love their servitude and will never dream of revolution.",
    title: "Brave New World Revisited",
    author: "Aldous Huxley",
  },
  {
    quote: "There is no greater agony than bearing an untold story inside you.",
    title: "I Know Why the Caged Bird Sings",
    author: "Maya Angelou",
  },
  {
    quote: "As he read, I fell in love the way you fall asleep: slowly, and then all at once.",
    title: "The Fault in Our Stars",
    author: "John Green",
  },
  {
    quote: "Anything worth dying for is certainly worth living for.",
    title: "Catch-22",
    author: "Joseph Heller",
  },
  {
    quote: "All the world is made of faith, and trust, and pixie dust.",
    title: "Peter Pan",
    author: "J.M. Barrie",
  },
  {
    quote: "Get busy living or get busy dying.",
    title: "Rita Hayworth and Shawshank Redemption",
    author: "Stephen King",
  },
  {
    quote: "‘But man is not made for defeat,’ he said. ‘A man can be destroyed but not defeated.’",
    title: "The Old Man and the Sea",
    author: "Ernest Hemingway",
  },
  {
    quote: "All we can know is that we know nothing. And that’s the height of human wisdom.",
    title: "War and Peace",
    author: "Leo Tolstoy",
  },
  {
    quote: "There is nothing like looking, if you want to find something. You certainly usually find something, if you look, but it is not always quite the something you were after.",
    title: "The Hobbit",
    author: "J.R.R. Tolkien",
  },
  {
    quote: "Life offers up these moments of joy despite everything.",
    title: "Normal People",
    author: "Sally Rooney",
  },
  {
    quote: "The world may be mean, but people don’t have to be, not if they refuse.",
    title: "The Underground Railroad",
    author: "Colson Whitehead",
  },
  {
    quote: "We had made a fetish out of our misfortune, fallen in love with it.",
    title: "The Dutch House",
    author: "Ann Patchett",
  },
  {
    quote: "Just like a murderer jumps out of nowhere in an alley, love jumped out in front of us and struck us both at once",
    title: "The Master and Margarita",
    author: "Mikhail Bulgakov",
  },
  {
    quote: "Life changes in the instant. The ordinary instant.",
    title: "The Year of Magical Thinking",
    author: "Joan Didion",
  },
  {
    quote: "I have a theory that selflessness and bravery aren’t all that different.",
    title: "Divergent",
    author: "Veronica Roth",
  },
  {
    quote: "That’s the thing about books. They let you travel without moving your feet.",
    title: "The Namesake",
    author: "Jhumpa Lahiri",
  },
  {
    quote: "We don’t have time, Nephew, time has us. It holds us in its mouth like an owl holds a field mouse.",
    title: "There There",
    author: "Tommy Orange",
  },
  {
    quote: "I have been bent and broken, but - I hope - into a better shape.",
    title: "Great Expectations",
    author: "Charles Dickens",
  },
  {
    quote: "Though sympathy alone can’t alter facts, it can help to make them more bearable.",
    title: "Dracula",
    author: "Bram Stoker",
  }
];

const quoteFade = document.querySelector("#quote-fade");
const quoteTextEl = document.querySelector("#book-quote-text");
const quoteTitleEl = document.querySelector("#book-quote-title");
const quoteAuthorEl = document.querySelector("#book-quote-author");

const QUOTE_INTERVAL_MS = 10000;
const QUOTE_FADE_MS = 500;

let currentQuoteIndex = Math.floor(Math.random() * bookQuotes.length);

function pickNextQuoteIndex() {
  if (bookQuotes.length < 2) return currentQuoteIndex;
  let nextIndex;
  do {
    nextIndex = Math.floor(Math.random() * bookQuotes.length);
  } while (nextIndex === currentQuoteIndex);
  return nextIndex;
}

function renderQuote(index) {
  const quote = bookQuotes[index];
  quoteTextEl.textContent = quote.quote;
  quoteTitleEl.textContent = quote.title;
  quoteAuthorEl.textContent = quote.author;
}

function showNextQuote() {
  currentQuoteIndex = pickNextQuoteIndex();

  if (!quoteFade) {
    renderQuote(currentQuoteIndex);
    return;
  }

  quoteFade.classList.add("is-swapping");
  window.setTimeout(() => {
    renderQuote(currentQuoteIndex);
    quoteFade.classList.remove("is-swapping");
  }, QUOTE_FADE_MS);
}

renderQuote(currentQuoteIndex);

if (bookQuotes.length > 1) {
  window.setInterval(showNextQuote, QUOTE_INTERVAL_MS);
}

if ("IntersectionObserver" in window) {
  const revealTargets = document.querySelectorAll(
    ".hero-copy, .hero-identity, .section-heading, .tool-card, .manifesto"
  );

  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15, rootMargin: "0px 0px -60px 0px" }
  );

  revealTargets.forEach((el) => {
    el.classList.add("reveal");
    revealObserver.observe(el);
  });

  document.querySelector(".hero-copy").style.transitionDelay = "120ms";
  document
    .querySelectorAll(".tool-card")
    .forEach((el, i) => (el.style.transitionDelay = `${i * 90}ms`));
}

fetch("/api/public/stats")
  .then((res) => (res.ok ? res.json() : null))
  .then((stats) => {
    if (!stats) return;
    const itemsEl = document.querySelector("#lendery-stat-count");
    if (itemsEl && typeof stats.lendery_items === "number") {
      itemsEl.textContent = stats.lendery_items.toLocaleString();
    }
    const clubsEl = document.querySelector("#bookclub-stat-count");
    if (clubsEl && typeof stats.bookclub_clubs === "number") {
      clubsEl.textContent = stats.bookclub_clubs.toLocaleString();
    }
  })
  .catch(() => {});

const prefersReducedMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)"
).matches;
const supportsFinePointer = window.matchMedia("(pointer: fine)").matches;

if (!prefersReducedMotion && supportsFinePointer) {
  const maxTilt = 6;

  document.querySelectorAll(".lendery-card, .bookclub-card").forEach((card) => {
    card.addEventListener("mousemove", (event) => {
      const rect = card.getBoundingClientRect();
      const px = (event.clientX - rect.left) / rect.width;
      const py = (event.clientY - rect.top) / rect.height;
      const rotateY = (px - 0.5) * maxTilt * 2;
      const rotateX = (0.5 - py) * maxTilt * 2;
      card.style.setProperty("--tilt-x", `${rotateX}deg`);
      card.style.setProperty("--tilt-y", `${rotateY}deg`);
    });

    card.addEventListener("mouseleave", () => {
      card.style.setProperty("--tilt-x", "0deg");
      card.style.setProperty("--tilt-y", "0deg");
    });
  });
}
