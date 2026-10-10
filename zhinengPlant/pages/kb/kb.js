// pages/kb/kb.js
const api = require('../../utils/request')
const { imageFor } = require('../../utils/plant-images')

Page({
  data: { list: [] },
  onShow() {
    api.call('/knowledge/list').then(res => this.setData({
      list: (res.data || []).map(item => Object.assign({}, item, { image: imageFor(item.name) }))
    }))
  },
  goDetail(e) {
    wx.navigateTo({ url: '/pages/kbd/kbd?id=' + e.currentTarget.dataset.id })
  }
})
