# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - main [ref=e2]:
    - generic [ref=e6]:
      - button "New Chat" [ref=e9]:
        - img
        - text: New Chat
      - generic [ref=e11]:
        - img [ref=e19]
        - generic [ref=e25]:
          - button [ref=e26]:
            - img
          - generic [ref=e27]:
            - textbox "Type a message..." [ref=e28]
            - button "Send" [disabled]:
              - img
              - generic: Send
  - generic [ref=e33] [cursor=pointer]:
    - button "Open Next.js Dev Tools" [ref=e34]:
      - img [ref=e35]
    - generic [ref=e38]:
      - button "Open issues overlay" [ref=e39]:
        - generic [ref=e40]:
          - generic [ref=e41]: "1"
          - generic [ref=e42]: "2"
        - generic [ref=e43]:
          - text: Issue
          - generic [ref=e44]: s
      - button "Collapse issues badge" [ref=e45]:
        - img [ref=e46]
  - alert [ref=e48]
```