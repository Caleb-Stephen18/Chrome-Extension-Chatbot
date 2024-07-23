chrome.tabs.onRemoved.addListener(function(tabId, removeInfo) {
  chrome.storage.local.remove([`chatHistory_${tabId}`, `pageProcessed_${tabId}`], function() {
    console.log(`Chat history and page processed state cleared for tab ${tabId}`);
  });
});