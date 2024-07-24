let chatHistory = [];
let currentTabId;

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function showTypingIndicator() {
  const indicator = document.createElement('div');
  indicator.className = 'typing-indicator';
  indicator.innerHTML = '<span></span><span></span><span></span>';
  document.getElementById('chatbox').appendChild(indicator);
  document.getElementById('chatbox').scrollTop = document.getElementById('chatbox').scrollHeight;
}

function hideTypingIndicator() {
  const indicator = document.getElementById('chatbox').querySelector('.typing-indicator');
  if (indicator) {
    indicator.remove();
  }
}

function renderChatHistory() {
  const chatbox = document.getElementById('chatbox');
  chatbox.innerHTML = '';
  chatHistory.forEach(msg => {
    if (msg.isSuggestedQuestion) {
      addSuggestedQuestion(msg.message, false);
    } else {
      addMessage(msg.sender, msg.message, msg.className, false);
    }
  });
}

function addMessage(sender, message, className, shouldSave = true) {
  const chatbox = document.getElementById('chatbox');
  const messageElement = document.createElement('div');
  messageElement.className = `message ${className}`;
  messageElement.textContent = message;
  chatbox.appendChild(messageElement);
  chatbox.scrollTop = chatbox.scrollHeight;

  setTimeout(() => messageElement.classList.add('show'), 10);

  if (shouldSave) {
    chatHistory.push({sender, message, className, isSuggestedQuestion: false});
    chrome.storage.local.set({[`chatHistory_${currentTabId}`]: chatHistory});
  }

  return messageElement;
}

function addSuggestedQuestion(question, shouldSave = true) {
  const chatbox = document.getElementById('chatbox');
  const questionElement = document.createElement('div');
  questionElement.className = 'message suggested-question';
  
  const iconElement = document.createElement('img');
  iconElement.className = 'icon';
  iconElement.src = 'ai-icon.png';
  
  const textElement = document.createElement('span');
  textElement.textContent = question;
  
  questionElement.appendChild(iconElement);
  questionElement.appendChild(textElement);
  
  questionElement.addEventListener('click', () => {
    document.getElementById('userInput').value = question;
    sendMessage();
  });
  
  chatbox.appendChild(questionElement);
  chatbox.scrollTop = chatbox.scrollHeight;

  if (shouldSave) {
    chatHistory.push({message: question, isSuggestedQuestion: true});
    chrome.storage.local.set({[`chatHistory_${currentTabId}`]: chatHistory});
  }
}

async function sendMessage(message = null) {
  const query = message || document.getElementById('userInput').value.trim();
  if (query) {
    addMessage('You', query, 'user');
    document.getElementById('userInput').value = '';

    showTypingIndicator();

    try {
      const response = await fetch('http://localhost:5000/ask_question', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query,
        }),
      });
      const data = await response.json();
      hideTypingIndicator();
      console.log("Received answer:", data);
      
      addMessage('Auralis', data.answer, 'ai');
      await delay(1000);
      
      if (data.suggested_questions && data.suggested_questions.length > 0) {
        addMessage('Auralis', 'Here are some suggested questions:', 'ai');
        await delay(1000);
        for (let question of data.suggested_questions) {
          addSuggestedQuestion(question);
          await delay(500);
        }
      }
    } catch (error) {
      hideTypingIndicator();
      console.error('Error:', error);
      addMessage('System', 'Failed to get response from server', 'ai');
    }
  }
}

async function displayInitialQuestions(retries = 3) {
  for (let attempt = 0; attempt < retries; attempt++) {
    showTypingIndicator();
    try {
      const response = await fetch('http://localhost:5000/get_initial_questions');
      const data = await response.json();
      console.log("Received initial questions:", data);
      
      if (data.suggested_questions && data.suggested_questions.length > 0) {
        hideTypingIndicator();
        addMessage('Auralis', 'Here are some suggested questions to get started:', 'ai');
        await delay(1000);
        for (let question of data.suggested_questions) {
          addSuggestedQuestion(question);
          await delay(500);
        }
        return; // Success, exit the function
      }
      
      console.warn(`No suggested questions received on attempt ${attempt + 1}`);
      if (attempt < retries - 1) {
        await delay(2000); // Wait before retrying
      }
    } catch (error) {
      console.error('Error:', error);
      if (attempt < retries - 1) {
        await delay(2000); // Wait before retrying
      }
    }
  }
  
  // If we've exhausted all retries and still have no questions
  addMessage('Auralis', 'I am ready to assist you. Feel free to ask me anything!', 'ai');
}

document.addEventListener('DOMContentLoaded', async function() {
  const userInput = document.getElementById('userInput');
  const sendBtn = document.getElementById('sendBtn');
  const closeIcon = document.getElementById('closeIcon');

  chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
    if (tabs[0]) {
      currentTabId = tabs[0].id;
      chrome.storage.local.get([`chatHistory_${currentTabId}`], async function(result) {
        chatHistory = result[`chatHistory_${currentTabId}`] || [];
        renderChatHistory();
        
        if (chatHistory.length === 0) {
          addMessage('Auralis', 'I am Auralis, how can I help you today?', 'ai');
          // await delay(1000);
          await displayInitialQuestions();
        }
      });
    }
  });

  sendBtn.addEventListener('click', () => sendMessage());
  userInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') sendMessage();
  });

  closeIcon.addEventListener('click', () => {
    window.close();
  });
});