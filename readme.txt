----for testing widget kindly run 
/test-widget/ 
also clear local storage for new room creation ,every time we open the widget will create new room on refresh 

----we can connect to admin chat by connecting to the rooms avialable with matching the room id 
/agent-chat/room-id/


----for locally User chat & Admin chat 
can uncomment the code which include html file so that we can we can check what we had made or the chat is initiating or not 


----Here we are using Redis for chat-cache , MongoDB for database by using pymongo,AWS S3 for files upload  and uvicorn as a service for asgi web application 

----we had made the API for userchat , agentchat, agentnotes, user-uploadfile, widget creation (CRUD)


