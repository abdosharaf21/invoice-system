/**
 * Admin users API client — consuming the /api/users blueprint (admin only).
 */

import { api } from "../api/client.js";

export function listUsers() {
  return api.get("/api/users/");
}

export function getUser(userId) {
  return api.get(`/api/users/${userId}`);
}

export function createUser(payload) {
  return api.post("/api/users/", payload);
}

export function updateUser(userId, payload) {
  return api.put(`/api/users/${userId}`, payload);
}

export function resetUserPassword(userId, newPassword) {
  return api.put(`/api/users/${userId}/password`, { new_password: newPassword });
}

export function activateUser(userId) {
  return api.put(`/api/users/${userId}/activate`);
}

export function deactivateUser(userId) {
  return api.put(`/api/users/${userId}/deactivate`);
}

export function deleteUser(userId) {
  return api.del(`/api/users/${userId}`);
}