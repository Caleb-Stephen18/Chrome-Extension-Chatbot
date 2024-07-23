console.log("Auralis content script loaded");

chrome.runtime.onMessage.addListener(function(request, sender, sendResponse) {
  console.log("Content script received message:", request);
  if (request.action === "getPageContent") {
    console.log("Sending page content");
    sendResponse({content: document.body.innerText});
  } else {
    console.log("Unknown action:", request.action);
  }
  return true;  // Indicates that the response is sent asynchronously
});